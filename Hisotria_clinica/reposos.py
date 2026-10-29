"""Medical approval and immutable version storage, including review concurrency checks."""
from datetime import date, timedelta
from functools import wraps
import hashlib
import json

from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, OperationalError, transaction
from django.db.models import F, Q
from django.utils import timezone

from LoginRegister.access import require_capability
from .models import Atencion, AuditoriaClinica, ConstanciaReposo, Estudiante
from .pdf_reposos import render_reposo, TEMPLATE_REVISION
from .reports import REPORT_ZONE
from .services import histories_for


REVIEW_SALT = 'uptag.reposo.review.v1'
REVIEW_SECONDS = 1800
DRAFT_FIELDS = {'motivo_reposo', 'dias', 'fecha_inicio'}


def _atomic_action(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            with transaction.atomic():
                return function(*args, **kwargs)
        except IntegrityError as exc:
            raise ValidationError('El reposo cambió o ya tiene otra versión. Actualiza la página.') from exc
        except OperationalError as exc:
            if 'locked' in str(exc).lower() or 'busy' in str(exc).lower():
                raise ValidationError('Otra operación está actualizando los datos. Revisa de nuevo antes de continuar.') from exc
            raise
    return wrapped


def _history(actor, history_id):
    actor = require_capability(actor, 'manage_reposo')
    history = histories_for(actor).select_related('medico', 'atencion').get(pk=history_id)
    if history.medico_id != actor.pk:
        raise PermissionDenied('Solo el médico responsable registrado en la consulta puede preparar o aprobar su reposo.')
    if not all((getattr(history, field) or '').strip() for field in ['motivo_consulta', 'diagnostico', 'tratamiento']):
        raise ValidationError('La consulta debe tener la información clínica obligatoria completa.')
    if history.atencion_id and (history.atencion.estado != Atencion.Estado.ATENDIDO or history.atencion.paciente_id != history.estudiante_id):
        raise ValidationError('La atención no está finalizada o no corresponde al paciente.')
    patient = history.estudiante
    if not all((getattr(patient, field) or '').strip() for field in ['nombre', 'apellido', 'cedula']):
        raise ValidationError('El paciente requiere nombres, apellidos y cédula registrados.')
    if patient.tipo_paciente not in Estudiante.Tipo.values:
        raise ValidationError('Confirma expresamente la categoría del paciente antes de preparar el documento.')
    if not history.fecha_consulta or history.fecha_consulta > timezone.localdate(timezone=REPORT_ZONE) or history.fecha_consulta < patient.fecha_nacimiento:
        raise ValidationError('La fecha de consulta debe ser coherente con el nacimiento y no ser futura.')
    return actor, history


def _data(data):
    if set(data) != DRAFT_FIELDS:
        raise ValidationError('Indica exclusivamente motivo, días y fecha de inicio del reposo.')
    reason, days, start = data['motivo_reposo'], data['dias'], data['fecha_inicio']
    if not isinstance(reason, str) or not reason.strip():
        raise ValidationError('El motivo clínico del reposo es obligatorio.')
    if type(days) is not int or days < 1 or type(start) is not date:
        raise ValidationError('Indica días enteros positivos y una fecha de inicio válida.')
    try:
        end = start + timedelta(days=days-1)
    except (OverflowError, ValueError) as exc:
        raise ValidationError('El período de reposo excede las fechas admitidas.') from exc
    return {'motivo_reposo': reason.strip(), 'dias': days, 'fecha_inicio': start, 'fecha_fin': end}


def _record(record):
    return {key: value.isoformat() if isinstance(value, date) else value for key in
            ['id', 'numero_version', 'estado', 'revision', 'motivo_reposo', 'dias', 'fecha_inicio', 'fecha_fin', 'motivo_correccion']
            for value in [getattr(record, key)]}


def _audit(actor, record, action, before=None):
    after = _record(record)
    if record.estado == ConstanciaReposo.Estado.EMITIDA:
        after.update(pdf_sha256=record.pdf_sha256, aprobado_por=record.aprobado_por_id, aprobado_en=record.aprobado_en.isoformat())
    AuditoriaClinica.objects.create(historia_id=record.historia_id, usuario=actor, motivo=action,
                                    anteriores={'constancia_reposo': before} if before else {},
                                    nuevos={'constancia_reposo': after})


def reposos_for(actor, history_id):
    actor = require_capability(actor, 'export_clinical')
    histories_for(actor).get(pk=history_id)
    return ConstanciaReposo.objects.filter(historia_id=history_id).filter(
        Q(estado='emitida') | Q(historia__medico_id=actor.pk)).defer('pdf', 'datos_emitidos')


@_atomic_action
def create_reposo_draft(*, actor, history_id, data, previous_id=None, correction_reason=''):
    actor, history = _history(actor, history_id)
    data = _data(data)
    if ConstanciaReposo.objects.filter(historia=history, estado='borrador').exists():
        raise ValidationError('Ya existe un borrador para esta consulta. Revísalo antes de preparar otra versión.')
    latest = ConstanciaReposo.objects.filter(historia=history, estado='emitida').defer('pdf', 'datos_emitidos').first()
    previous = None
    if latest:
        if str(previous_id) != str(latest.pk):
            raise ValidationError('La corrección debe partir de la última versión emitida.')
        if not isinstance(correction_reason, str) or not correction_reason.strip():
            raise ValidationError('Indica el motivo obligatorio de la nueva versión.')
        previous = latest
    elif previous_id is not None:
        raise ValidationError('La versión anterior no corresponde a esta consulta.')
    record = ConstanciaReposo(historia=history, anterior=previous,
        numero_version=previous.numero_version+1 if previous else 1, creado_por=actor,
        motivo_correccion=(correction_reason or '').strip(), **data)
    record.full_clean()
    record.save()
    _audit(actor, record, 'Preparación de constancia de reposo')
    return record


@_atomic_action
def update_reposo_draft(*, actor, reposo_id, data, expected_revision, reason):
    actor = require_capability(actor, 'manage_reposo')
    record = ConstanciaReposo.objects.get(pk=reposo_id)
    _history(actor, record.historia_id)
    if record.estado != 'borrador' or record.revision != expected_revision:
        raise ValidationError('La constancia cambió o ya fue emitida. No se modifica una versión definitiva.')
    if not isinstance(reason, str) or not reason.strip():
        raise ValidationError('El motivo de modificación del borrador es obligatorio.')
    before = _record(record)
    values = _data(data)
    for name, value in values.items():
        setattr(record, name, value)
    record.full_clean()
    changed = ConstanciaReposo.objects.filter(pk=record.pk, estado='borrador', revision=expected_revision).update(
        **values, revision=F('revision')+1, actualizado_en=timezone.now())
    if changed != 1:
        raise ValidationError('La constancia cambió. Actualiza la página.')
    record.refresh_from_db()
    _audit(actor, record, 'Modificación de borrador de reposo: '+reason.strip(), before)
    return record


def _snapshot(actor, record):
    _, history = _history(actor, record.historia_id)
    patient = history.estudiante
    values = _data({key: getattr(record, key) for key in DRAFT_FIELDS})
    if values['fecha_fin'] != record.fecha_fin:
        raise ValidationError('Los días y el período guardado no coinciden. Revisa el borrador.')
    if record.fecha_inicio < patient.fecha_nacimiento:
        raise ValidationError('El período no puede comenzar antes del nacimiento del paciente.')
    latest = ConstanciaReposo.objects.filter(historia_id=record.historia_id, estado='emitida').defer('pdf', 'datos_emitidos').first()
    if latest:
        if record.anterior_id != latest.pk or record.numero_version != latest.numero_version+1 or not record.motivo_correccion.strip():
            raise ValidationError('La cadena de versiones o el motivo de corrección requieren revisión.')
    elif record.anterior_id is not None or record.numero_version != 1:
        raise ValidationError('La primera versión debe iniciar una cadena nueva para esta consulta.')
    return {'formato': 'FOR-SSS-07', 'schema': 2, 'plantilla_revision': TEMPLATE_REVISION, 'constancia_id': record.pk,
        'historia_id': history.pk, 'historia_version': history.version,
        'numero_version': record.numero_version, 'anterior_id': record.anterior_id,
        'motivo_correccion': record.motivo_correccion,
        'fecha_consulta': history.fecha_consulta.isoformat(),
        'fecha_emision': timezone.localdate(timezone=REPORT_ZONE).isoformat(),
        'motivo_reposo': record.motivo_reposo, 'dias': record.dias,
        'fecha_inicio': record.fecha_inicio.isoformat(), 'fecha_fin': record.fecha_fin.isoformat(),
        'paciente': {'id': patient.pk, 'nombre_completo': f'{patient.nombre} {patient.apellido}',
                    'cedula': patient.cedula, 'tipo_paciente': patient.tipo_paciente,
                    'pnf': patient.pnf if patient.tipo_paciente == 'estudiante' else ''},
        'medico': {'id': history.medico_id, 'nombre_completo': str(history.medico)}}


def _digest(snapshot):
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()


def review_reposo(*, actor, reposo_id):
    actor = require_capability(actor, 'manage_reposo')
    record = ConstanciaReposo.objects.get(pk=reposo_id)
    if record.estado != 'borrador':
        raise ValidationError('La constancia ya fue emitida. Consulta su PDF guardado.')
    snapshot = _snapshot(actor, record)
    content = render_reposo(snapshot, draft=True)
    token = signing.dumps({'id': record.pk, 'revision': record.revision, 'actor': actor.pk,
                           'digest': _digest(snapshot)}, salt=REVIEW_SALT)
    return record, snapshot, content, token


@_atomic_action
def approve_reposo(*, actor, reposo_id, expected_revision, review_token, confirmed):
    actor = require_capability(actor, 'manage_reposo')
    record = ConstanciaReposo.objects.get(pk=reposo_id)
    if record.estado != 'borrador' or record.revision != expected_revision:
        raise ValidationError('La constancia cambió o ya fue emitida. Revisa la versión actual.')
    if confirmed is not True:
        raise ValidationError('Debes confirmar que revisaste y apruebas el documento.')
    if not isinstance(review_token, str):
        raise ValidationError('La revisión no es válida. Abre de nuevo la vista previa.')
    snapshot = _snapshot(actor, record)
    try:
        reviewed = signing.loads(review_token, salt=REVIEW_SALT, max_age=REVIEW_SECONDS)
    except (signing.BadSignature, TypeError, ValueError) as exc:
        raise ValidationError('La revisión no es válida o caducó. Abre de nuevo la vista previa.') from exc
    if reviewed != {'id': record.pk, 'revision': record.revision, 'actor': actor.pk, 'digest': _digest(snapshot)}:
        raise ValidationError('Los datos cambiaron desde la vista previa. Debes revisarlos nuevamente.')
    content = render_reposo(snapshot, draft=False)
    before = _record(record)
    now = timezone.now()
    changed = ConstanciaReposo.objects.filter(pk=record.pk, estado='borrador', revision=expected_revision).update(
        estado='emitida', datos_emitidos=snapshot, pdf=content, pdf_sha256=hashlib.sha256(content).hexdigest(),
        aprobado_por=actor, aprobado_en=now, actualizado_en=now, revision=F('revision')+1)
    if changed != 1:
        raise ValidationError('Otra operación aprobó o modificó el borrador. Actualiza la página.')
    record.refresh_from_db()
    _audit(actor, record, 'Aprobación médica y emisión de constancia de reposo', before)
    return record


def issued_reposo_pdf(*, actor, reposo_id):
    require_capability(actor, 'export_clinical')
    record = ConstanciaReposo.objects.get(pk=reposo_id)
    if record.estado != 'emitida':
        raise ValidationError('El documento es un borrador y no tiene PDF definitivo aprobado.')
    content = bytes(record.pdf)
    if not content or hashlib.sha256(content).hexdigest() != record.pdf_sha256:
        raise ValidationError('La integridad del PDF guardado no pudo verificarse. No se regenerará automáticamente.')
    return record, content
