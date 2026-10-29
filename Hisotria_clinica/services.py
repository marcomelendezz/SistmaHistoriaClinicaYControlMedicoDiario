from datetime import date, datetime, timedelta
import re

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F, Q, Value
from django.db.models.functions import Replace, Trim, Upper
from django.utils import timezone

from LoginRegister.access import require_capability
from .models import Atencion, AuditoriaClinica, AuditoriaPaciente, CambioEstadoAtencion, Estudiante, HistoriaClinica
from .daily_options import OPTION_CODES
from .medical_time import REPORT_ZONE


def patients_for(actor):
    require_capability(actor, 'read_clinical')
    # Approved institutional staff share the central patient directory.
    return Estudiante.objects.all().order_by('apellido', 'nombre')


def histories_for(actor):
    require_capability(actor, 'read_clinical')
    return HistoriaClinica.objects.select_related('estudiante').order_by('-fecha_consulta', '-pk')


PATIENT_FIELDS = {'nombre', 'apellido', 'cedula', 'edo_civil', 'sexo', 'direccion',
    'contacto_emergencia', 'telefono', 'fecha_nacimiento', 'tipo_paciente', 'pnf', 'cargo_laboral',
    'lugar_nacimiento', 'parentesco_emergencia', 'telefono_emergencia'}
WORKER_TYPES = {Estudiante.Tipo.PROFESOR, Estudiante.Tipo.OBRERO_TECNICO, Estudiante.Tipo.ADMINISTRATIVO}


def identity_expression():
    return Upper(Replace(Replace(Replace(Trim('cedula'), Value('-'), Value('')), Value('.'), Value('')), Value(' '), Value('')))


def find_patients(actor, query):
    patients = patients_for(actor)
    query = query.strip()
    if not query:
        return patients
    key = re.sub(r'[-.\s]', '', query.upper())
    return patients.alias(identity_key=identity_expression()).filter(
        Q(nombre__icontains=query) | Q(apellido__icontains=query) | Q(cedula__icontains=query)
        | Q(cedula_clave=key) | Q(identity_key=key))


def validate_new_identity(value):
    value = str(value or '').strip().upper()
    if not value or len(value) > 20 or not re.fullmatch(r'[A-Z0-9]+(?:[-.][A-Z0-9]+)*', value) or not any(character.isdigit() for character in value):
        raise ValidationError('Indica una cédula de hasta 20 caracteres, con dígitos y, si corresponde, letras, guiones o puntos.')
    key = re.sub(r'[-. ]', '', value)
    if Estudiante.objects.alias(identity_key=identity_expression()).filter(Q(cedula_clave=key) | Q(identity_key=key)).exists():
        raise ValidationError('Ya existe un paciente con esta cédula. Busca y reutiliza su expediente.')
    return value


def patient_snapshot(patient):
    snapshot = {}
    for field in sorted(PATIENT_FIELDS | {'edad'}):
        value = getattr(patient, field)
        snapshot[field] = value.isoformat() if isinstance(value, date) else value
    return snapshot


def prepare_patient_data(data, *, existing=None):
    if set(data) - PATIENT_FIELDS:
        raise ValidationError('El registro administrativo no admite datos clínicos ni campos adicionales.')
    data = dict(data)
    category = data.get('tipo_paciente')
    if category not in Estudiante.Tipo.values:
        raise ValidationError('Selecciona uno de los cinco tipos de paciente.')
    if category != Estudiante.Tipo.ESTUDIANTE and data.get('pnf'):
        raise ValidationError('El PNF solo corresponde a estudiantes.')
    if category not in WORKER_TYPES and data.get('cargo_laboral'):
        raise ValidationError('El cargo solo corresponde a personal con vínculo laboral activo.')
    if existing:
        if 'cedula' in data and data['cedula'] != existing.cedula:
            raise ValidationError('No se puede cambiar la identificación histórica desde este formulario.')
    else:
        data['cedula'] = validate_new_identity(data.get('cedula'))
    return data


@transaction.atomic
def register_patient(*, actor, data):
    actor = require_capability(actor, 'manage_patients')
    data = prepare_patient_data(data)
    patient = Estudiante(**data, edad=0, cedula_clave=re.sub(r'[-. ]', '', data['cedula']))
    patient.full_clean()
    if patient.fecha_nacimiento > timezone.localdate():
        raise ValidationError('La fecha de nacimiento no puede estar en el futuro.')
    patient.edad = patient.edad_actual
    try:
        with transaction.atomic():
            patient.save()
    except IntegrityError as exc:
        raise ValidationError('No fue posible registrar el paciente. Revisa si la cédula ya existe.') from exc
    AuditoriaPaciente.objects.create(paciente=patient, usuario=actor, accion='registro', nuevos=patient_snapshot(patient))
    return patient


@transaction.atomic
def update_patient(*, actor, patient_id, data):
    actor = require_capability(actor, 'manage_patients')
    patient = Estudiante.objects.select_for_update().get(pk=patient_id)
    before = patient_snapshot(patient)
    original_birth = patient.fecha_nacimiento
    for field, value in prepare_patient_data(data, existing=patient).items():
        setattr(patient, field, value)
    patient.full_clean()
    if patient.fecha_nacimiento != original_birth:
        if patient.fecha_nacimiento > timezone.localdate():
            raise ValidationError('La fecha de nacimiento no puede estar en el futuro.')
        patient.edad = patient.edad_actual
    after = patient_snapshot(patient)
    changes = {field for field in before if before[field] != after[field]}
    if changes:
        patient.save(update_fields=sorted(changes))
        AuditoriaPaciente.objects.create(paciente=patient, usuario=actor, accion='modificacion',
            anteriores={field: before[field] for field in changes}, nuevos={field: after[field] for field in changes})
    return patient


CLINICAL_FIELDS = {'fecha_consulta', 'motivo_consulta', 'diagnostico', 'tratamiento', 'observaciones',
                   'enfermedad_actual', 'diagnostico_provisional'} | set(OPTION_CODES)


def validate_option_values(data):
    # Services do not accept truthy strings, integers, labels or inferred values.
    for code in OPTION_CODES:
        if code in data and type(data[code]) is not bool:
            raise ValidationError(f'La opción {code} debe ser verdadera o falsa.')


def attentions_for(actor):
    require_capability(actor, 'read_clinical')
    return Atencion.objects.select_related('paciente', 'registrada_por', 'actualizada_por')


@transaction.atomic
def register_arrival(*, actor, patient_id, arrival, reason, nurse_id=None, shift=''):
    actor = require_capability(actor, 'manage_attention')
    patient = patients_for(actor).get(pk=patient_id)
    if not isinstance(arrival, datetime):
        raise ValidationError('Indica la fecha y hora de llegada.')
    if timezone.is_naive(arrival):
        arrival = timezone.make_aware(arrival)
    if arrival > timezone.now() + timedelta(minutes=5):
        raise ValidationError('La llegada no puede registrarse en el futuro.')
    reason = (reason or '').strip()
    if not reason or len(reason) > 4000:
        raise ValidationError('Indica el motivo de visita (máximo 4000 caracteres).')
    shift = (shift or '').strip()
    if len(shift) > 50:
        raise ValidationError('El turno admite hasta 50 caracteres.')
    nurse = None
    if nurse_id is not None:
        from LoginRegister.models import Usuario
        nurse = Usuario.objects.filter(pk=nurse_id, is_active=True, approval_status=Usuario.Status.APPROVED,
                                       authorized_role=Usuario.Role.NURSE).first()
        if nurse is None:
            raise ValidationError('La enfermera responsable debe tener una cuenta activa y aprobada de enfermería.')
    if Atencion.objects.filter(paciente=patient, estado__in=['pendiente', 'en_atencion']).exists():
        raise ValidationError('El paciente ya tiene una atención abierta. Consulta la lista de atenciones.')
    try:
        with transaction.atomic():
            attention = Atencion.objects.create(paciente=patient, fecha_hora_llegada=arrival,
                motivo_visita=reason, registrada_por=actor, actualizada_por=actor,
                turno=shift, enfermera_responsable=nurse)
    except IntegrityError as exc:
        raise ValidationError('El paciente ya tiene una atención abierta.') from exc
    CambioEstadoAtencion.objects.create(atencion=attention, usuario=actor, anterior='', nuevo=attention.estado)
    return attention


def _set_state(attention, actor, target):
    updated = Atencion.objects.filter(pk=attention.pk, estado=attention.estado, version=attention.version).update(
        estado=target, actualizada_por=actor, actualizada_en=timezone.now(), version=F('version') + 1)
    if updated != 1:
        raise ValidationError('La atención cambió mientras trabajabas. Actualiza la página.')
    CambioEstadoAtencion.objects.create(atencion=attention, usuario=actor, anterior=attention.estado, nuevo=target)
    attention.refresh_from_db()
    return attention


@transaction.atomic
def transition_attention(*, actor, attention_id, target, expected_version):
    actor = require_capability(actor, 'manage_attention')
    attention = Atencion.objects.select_for_update().get(pk=attention_id)
    if attention.version != expected_version:
        raise ValidationError('La atención fue modificada. Actualiza la página.')
    allowed = {'pendiente': {'en_atencion', 'cancelado'}, 'en_atencion': {'cancelado'}}
    if target not in allowed.get(attention.estado, set()):
        raise ValidationError('Cambio de estado no permitido. Solo la consulta médica completa finaliza la atención.')
    return _set_state(attention, actor, target)


def clinical_snapshot(history):
    return {field: value.isoformat() if isinstance(value, date) else value
        for field in sorted(CLINICAL_FIELDS) for value in [getattr(history, field)]}


def validate_clinical_record(history, *, check_dates=True):
    for code, label in [('motivo_consulta', 'motivo de consulta'), ('diagnostico', 'diagnóstico'), ('tratamiento', 'tratamiento')]:
        if not isinstance(getattr(history, code), str) or not getattr(history, code).strip():
            raise ValidationError(f'Completa el {label}; no puede contener solamente espacios.')
    if check_dates and (history.fecha_consulta < history.estudiante.fecha_nacimiento or
                        history.fecha_consulta > timezone.localdate(timezone=REPORT_ZONE)):
        raise ValidationError('La fecha de consulta debe ser coherente con el nacimiento y no ser futura.')


@transaction.atomic
def create_history(*, actor, patient_id, data, attention_id=None):
    actor = require_capability(actor, 'write_clinical')
    if set(data) - CLINICAL_FIELDS:
        raise ValidationError('Campos clínicos no permitidos.')
    validate_option_values(data)
    data = {**dict.fromkeys(OPTION_CODES, False), **data}
    if attention_id is None:
        raise ValidationError('Primero registra la llegada y marca al paciente en atención.')
    attention = Atencion.objects.select_for_update().get(pk=attention_id)
    if attention.paciente_id != int(patient_id) or attention.estado != Atencion.Estado.EN_ATENCION:
        raise ValidationError('La consulta debe corresponder al paciente que está en atención.')
    history = HistoriaClinica(estudiante=attention.paciente, atencion=attention, medico=actor, **data)
    history.full_clean()
    validate_clinical_record(history)
    try:
        with transaction.atomic():
            history.save()
    except IntegrityError as exc:
        raise ValidationError('La atención ya tiene una consulta registrada.') from exc
    AuditoriaClinica.objects.create(historia=history, usuario=actor, motivo='Registro de consulta médica', nuevos=clinical_snapshot(history))
    _set_state(attention, actor, Atencion.Estado.ATENDIDO)
    return history


@transaction.atomic
def correct_history(*, actor, history_id, data, reason, expected_version):
    actor = require_capability(actor, 'write_clinical')
    if not (reason or '').strip():
        raise ValidationError('El motivo de corrección clínica es obligatorio.')
    if set(data) - CLINICAL_FIELDS:
        raise ValidationError('Campos clínicos no permitidos.')
    validate_option_values(data)
    history = HistoriaClinica.objects.select_for_update().get(pk=history_id)
    if history.version != expected_version:
        raise ValidationError('La historia cambió. Actualiza la página antes de corregirla.')
    before = clinical_snapshot(history)
    original_date = history.fecha_consulta
    for field, value in data.items():
        setattr(history, field, value)
    history.full_clean()
    # Historical dates are not silently rewritten when correcting another field.
    validate_clinical_record(history, check_dates=history.fecha_consulta != original_date)
    after = clinical_snapshot(history)
    changes = {field for field in before if before[field] != after[field]}
    if changes:
        values = {field: getattr(history, field) for field in changes}
        values['version'] = F('version') + 1
        if HistoriaClinica.objects.filter(pk=history.pk, version=expected_version).update(**values) != 1:
            raise ValidationError('Otra corrección fue guardada. Actualiza la página.')
        AuditoriaClinica.objects.create(historia=history, usuario=actor, motivo=reason.strip(),
            anteriores={field: before[field] for field in changes}, nuevos={field: after[field] for field in changes})
        history.refresh_from_db()
    return history


def register_patient_and_history(*, actor, patient_data, history_data):
    require_capability(actor, 'write_clinical')
    raise ValidationError('El registro combinado fue retirado. Registra la ficha y luego una llegada independiente.')
