"""Read-only report queries shared by the web report and FOR-SSS-02."""
from dataclasses import dataclass, field
from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.db.models import Exists, OuterRef
from django.db.models.functions import TruncDate
from django.utils import timezone

from LoginRegister.access import require_capability
from .models import Atencion, CambioEstadoAtencion
from .services import attentions_for, histories_for
from .daily_options import ADDITIONAL_OPTIONS, PROCEDURE_OPTIONS
from .medical_time import REPORT_ZONE


MAX_REPORT_DAYS = 366


def validate_period(start, end, *, allow_all=False):
    if start is None and end is None and allow_all:
        return
    if type(start) is not date or type(end) is not date:
        raise ValidationError('Selecciona una fecha o las dos fechas del rango.')
    if end < start:
        raise ValidationError('La fecha final no puede ser anterior a la inicial.')
    if (end - start).days + 1 > MAX_REPORT_DAYS:
        raise ValidationError(f'Consulta hasta {MAX_REPORT_DAYS} días por rango.')


@dataclass
class DailyTeam:
    doctor: object
    nurse: object
    shift: str
    rows: list = field(default_factory=list)


@dataclass
class ReportDay:
    date: date
    teams: list = field(default_factory=list)

    @property
    def count(self):
        return sum(len(team.rows) for team in self.teams)


@dataclass
class DailyReport:
    start: date
    end: date
    days: list
    legacy_count: int
    legacy_samples: list
    excluded_count: int
    excluded_samples: list

    @property
    def count(self):
        return sum(day.count for day in self.days)


@dataclass
class PendingReport:
    start: object
    end: object
    rows: list
    consulted_at: object

    @property
    def count(self):
        return len(self.rows)


def _age_on(birth, on_date):
    if not birth or birth > on_date:
        return None
    return on_date.year - birth.year - ((on_date.month, on_date.day) < (birth.month, birth.day))


def _incomplete_reason(attention):
    history = getattr(attention, 'historia', None)
    if not history:
        return 'No tiene una historia clínica relacionada.'
    if history.estudiante_id != attention.paciente_id:
        return 'El paciente de la historia no coincide con el de la atención.'
    if not attention.has_completion_trace:
        return 'No tiene un cambio a Atendido registrado en la trazabilidad.'
    if history.medico_id is None:
        return 'No tiene médico responsable registrado.'
    if not history.fecha_consulta or not all((getattr(history, name) or '').strip() for name in ['motivo_consulta', 'diagnostico', 'tratamiento']):
        return 'La información clínica obligatoria está incompleta.'
    return ''


def daily_report(*, actor, start, end):
    require_capability(actor, 'view_reports')
    validate_period(start, end)
    days = [ReportDay(start + timedelta(days=index)) for index in range((end - start).days + 1)]
    by_date = {day.date: day for day in days}
    teams = {}
    excluded_count, excluded_samples = 0, []
    completion_events = CambioEstadoAtencion.objects.filter(atencion_id=OuterRef('pk'), nuevo=Atencion.Estado.ATENDIDO)
    # The terminal state makes actualizada_en the stored completion time. An
    # Exists subquery checks traceability without multiplying rows by events.
    attentions = attentions_for(actor).filter(estado=Atencion.Estado.ATENDIDO).annotate(
        report_date=TruncDate('actualizada_en', tzinfo=REPORT_ZONE),
        has_completion_trace=Exists(completion_events),
    ).filter(report_date__range=(start, end)).select_related('historia__medico', 'enfermera_responsable').order_by(
        'report_date', 'historia__medico_id', 'enfermera_responsable_id', 'turno', 'actualizada_en', 'pk')
    for attention in attentions:
        problem = _incomplete_reason(attention)
        if problem:
            excluded_count += 1
            if len(excluded_samples) < 50:
                excluded_samples.append({'attention': attention, 'reason': problem})
            continue
        history = attention.historia
        day = by_date[attention.report_date]
        key = (day.date, history.medico_id, attention.enfermera_responsable_id, attention.turno)
        if key not in teams:
            team = DailyTeam(history.medico, attention.enfermera_responsable, attention.turno)
            teams[key] = team
            day.teams.append(team)
        teams[key].rows.append({'attention': attention, 'history': history,
            'options': [{'code': code, 'label': label, 'selected': getattr(history, code) is True}
                        for code, label in (*ADDITIONAL_OPTIONS, *PROCEDURE_OPTIONS)],
            'completed_at': timezone.localtime(attention.actualizada_en, REPORT_ZONE),
            'age': _age_on(attention.paciente.fecha_nacimiento, day.date)})
    legacy = histories_for(actor).filter(atencion__isnull=True, fecha_consulta__range=(start, end))
    return DailyReport(start, end, days, legacy.count(), list(legacy[:50]), excluded_count, excluded_samples)


def pending_report(*, actor, start=None, end=None):
    require_capability(actor, 'view_reports')
    validate_period(start, end, allow_all=True)
    attentions = attentions_for(actor).filter(estado=Atencion.Estado.PENDIENTE).select_related('enfermera_responsable')
    if start is not None:
        attentions = attentions.alias(arrival_date=TruncDate('fecha_hora_llegada', tzinfo=REPORT_ZONE)).filter(arrival_date__range=(start, end))
    return PendingReport(start, end, list(attentions.order_by('fecha_hora_llegada', 'pk')),
                         timezone.localtime(timezone.now(), REPORT_ZONE))
