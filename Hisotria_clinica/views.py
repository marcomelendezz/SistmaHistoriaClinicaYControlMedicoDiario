from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse
from django.urls import reverse
from urllib.parse import urlencode
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_safe, require_POST
from django.views.decorators.clickjacking import xframe_options_sameorigin

from LoginRegister.access import capability_required, has_capability
from .forms import CambioEstadoForm, CorreccionClinicaForm, EstudianteForm, FiltroAtencionesForm, FiltroReportesForm, HistoriaClinicaForm, LlegadaForm
from .services import (attentions_for, correct_history, create_history, find_patients, histories_for, patients_for, register_arrival, register_patient, transition_attention, update_patient)
from .models import Atencion, Estudiante, HistoriaClinica
from .reports import daily_report, pending_report, REPORT_ZONE
from .daily_options import ADDITIONAL_OPTIONS, PROCEDURE_OPTIONS


def search_patients(actor, query, category=''):
    patients = find_patients(actor, query)
    if category == 'por_verificar':
        patients = patients.filter(tipo_paciente__isnull=True)
    elif category:
        patients = patients.filter(tipo_paciente=category) if category in Estudiante.Tipo.values else patients.none()
    return patients


@capability_required('manage_patients')
def registro_paciente_view(request):
    form = EstudianteForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        try:
            patient = register_patient(actor=request.user, data=form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, 'Paciente registrado correctamente.')
            return redirect('detalle_paciente', pk=patient.pk)
    return render(request, 'historia/paciente.html', {'form': form})


@capability_required('manage_patients')
def editar_paciente_view(request, pk):
    patient = get_object_or_404(patients_for(request.user), pk=pk)
    form = EstudianteForm(request.POST if request.method == 'POST' else None, instance=patient)
    if request.method == 'POST' and form.is_valid():
        try:
            update_patient(actor=request.user, patient_id=pk, data=form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, 'Datos personales actualizados; se conservan las consultas previas.')
            return redirect('detalle_paciente', pk=pk)
    return render(request, 'historia/paciente.html', {'form': form, 'patient': patient})


@capability_required('read_clinical')
@require_safe
def lista_pacientes_view(request):
    query = request.GET.get('q', '').strip()
    category = request.GET.get('tipo', '')
    return render(request, 'historia/pacientes.html', {
        'patients': search_patients(request.user, query, category), 'query': query,
        'category': category, 'types': Estudiante.Tipo.choices,
    })


@capability_required('read_clinical')
@require_safe
def detalle_paciente_view(request, pk):
    patient = get_object_or_404(patients_for(request.user), pk=pk)
    return render(request, 'historia/expediente.html', {
        'patient': patient, 'histories': histories_for(request.user).filter(estudiante=patient),
        'changes': patient.cambios_personales.select_related('usuario')[:50],
    })


def patient_by_id(actor, value):
    try:
        patient_id = int(value)
    except (TypeError, ValueError):
        raise Http404('Paciente no válido.') from None
    return get_object_or_404(patients_for(actor), pk=patient_id)


@capability_required('manage_patients')
@require_safe
def registro_historia_view(request):
    # Historical navigation remains valid; combined writes are no longer exposed.
    return redirect('registro_paciente')


@capability_required('manage_attention')
def nueva_consulta_view(request):
    query = request.GET.get('q', '').strip()
    category = request.GET.get('tipo', '')
    patients = search_patients(request.user, query, category)
    selected_id = request.POST.get('estudiante') or request.GET.get('estudiante')
    selected = patient_by_id(request.user, selected_id) if selected_id else None
    form = LlegadaForm(request.POST if request.method == 'POST' else None,
                       initial={'arrival': timezone.localtime().replace(second=0, microsecond=0)})
    if request.method == 'POST' and form.is_valid():
        if selected is None:
            form.add_error(None, 'Busca y selecciona un paciente existente.')
        else:
            data = dict(form.cleaned_data)
            nurse = data.pop('nurse')
            try:
                register_arrival(actor=request.user, patient_id=selected.pk,
                                 nurse_id=nurse.pk if nurse else None, **data)
            except ValidationError as exc:
                form.add_error(None, str(exc))
            else:
                messages.success(request, 'Llegada registrada. El paciente está pendiente de atención.')
                return redirect('lista_atenciones')
    return render(request, 'historia/nueva_consulta.html', {'form': form, 'patients': patients,
        'selected': selected, 'query': query, 'category': category, 'types': Estudiante.Tipo.choices})


@capability_required('read_clinical')
@require_safe
def lista_atenciones_view(request):
    initial_date = timezone.localdate().isoformat()
    form = FiltroAtencionesForm(request.GET if request.GET else {'fecha': initial_date})
    attentions = attentions_for(request.user).select_related('historia')
    if form.is_valid():
        date_value = form.cleaned_data['fecha']
        state = form.cleaned_data['estado']
        query = form.cleaned_data['q'].strip()
        if date_value:
            attentions = attentions.filter(fecha_hora_llegada__date=date_value)
        if state:
            attentions = attentions.filter(estado=state)
        if query:
            attentions = attentions.filter(paciente__in=find_patients(request.user, query))
    else:
        attentions = attentions.none()
    return render(request, 'historia/atenciones.html', {'form': form, 'attentions': attentions})


@capability_required('manage_attention')
@require_POST
def cambiar_estado_view(request, pk):
    get_object_or_404(attentions_for(request.user), pk=pk)
    form = CambioEstadoForm(request.POST)
    if form.is_valid():
        try:
            transition_attention(actor=request.user, attention_id=pk, **form.cleaned_data)
        except ValidationError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, 'Estado de atención actualizado.')
    else:
        messages.error(request, 'No se pudo cambiar el estado. Actualiza la lista y revisa la selección.')
    return redirect('lista_atenciones')


@capability_required('write_clinical')
def consulta_medica_view(request, pk):
    attention = get_object_or_404(attentions_for(request.user), pk=pk)
    if attention.estado != Atencion.Estado.EN_ATENCION:
        messages.error(request, 'La consulta requiere que el paciente esté en atención.')
        return redirect('lista_atenciones')
    form = HistoriaClinicaForm(request.POST if request.method == 'POST' else None,
        initial={'fecha_consulta': timezone.localdate(timezone=REPORT_ZONE), 'motivo_consulta': attention.motivo_visita})
    if request.method == 'POST' and form.is_valid():
        try:
            history = create_history(actor=request.user, patient_id=attention.paciente_id,
                attention_id=attention.pk, data=form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, 'Consulta registrada y atención finalizada.')
            return redirect('detalle_historia', pk=history.pk)
    return render(request, 'historia/consulta_medica.html', {'form': form, 'attention': attention})


@capability_required('write_clinical')
def corregir_historia_view(request, pk):
    history = get_object_or_404(histories_for(request.user), pk=pk)
    form = CorreccionClinicaForm(request.POST if request.method == 'POST' else None,
        instance=history, initial={'expected_version': history.version})
    if request.method == 'POST' and form.is_valid():
        data = dict(form.cleaned_data)
        reason = data.pop('reason')
        version = data.pop('expected_version')
        try:
            correct_history(actor=request.user, history_id=pk, data=data, reason=reason, expected_version=version)
        except ValidationError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, 'Corrección guardada con su motivo e historial de cambios.')
            return redirect('detalle_historia', pk=pk)
    return render(request, 'historia/correccion.html', {'form': form, 'historia': history})


@capability_required('read_clinical')
@require_safe
def lista_historia_view(request):
    query = request.GET.get('q', '').strip()
    category = request.GET.get('tipo', '')
    if request.GET.get('estudiante'):
        patient = patient_by_id(request.user, request.GET['estudiante'])
        return redirect('detalle_paciente', pk=patient.pk)
    return render(request, 'historia/pacientes.html', {'patients': search_patients(request.user, query, category),
        'query': query, 'category': category, 'types': Estudiante.Tipo.choices})


@capability_required('read_clinical')
@require_safe
def detalle_historia_view(request, pk):
    history = get_object_or_404(histories_for(request.user), pk=pk)
    reposos = []
    if has_capability(request.user, 'export_clinical'):
        from .reposos import reposos_for
        reposos = reposos_for(request.user, history.pk)
    return render(request, 'historia/detalle.html', {'historia': history,
        'reposos': reposos,
        'changes': history.cambios_clinicos.select_related('usuario')})


def _history_pdf_content(request, pk):
    from .pdf_histories import clinical_history_pdf
    try:
        return clinical_history_pdf(actor=request.user, history_id=pk), None
    except HistoriaClinica.DoesNotExist as exc:
        raise Http404('No se encontró la consulta.') from exc
    except ValidationError as exc:
        return None, render(request, 'historia/documentos/error_historia.html',
                            {'errors': exc.messages, 'history_id': pk}, status=422)


@capability_required('export_clinical')
@require_safe
@xframe_options_sameorigin
def historia_pdf_view(request, pk):
    content, error = _history_pdf_content(request, pk)
    if error is not None:
        return error
    response = HttpResponse(content, content_type='application/pdf')
    disposition = 'attachment' if request.GET.get('download') == '1' else 'inline'
    response['Content-Disposition'] = f'{disposition}; filename="FOR-SSS-04_consulta-{pk}.pdf"'
    return response


@capability_required('export_clinical')
@require_safe
def imprimir_historia_view(request, pk):
    _, error = _history_pdf_content(request, pk)
    if error is not None:
        return error
    return render(request, 'historia/documentos/imprimir_historia.html',
                  {'pdf_url': reverse('historia_pdf', args=[pk]), 'history_id': pk})


@capability_required('view_reports')
@require_safe
def registro_diario_view(request):
    data = request.GET if request.GET else {'fecha': timezone.localdate(timezone=REPORT_ZONE).isoformat()}
    form = FiltroReportesForm(data)
    report = None
    if form.is_valid():
        report = daily_report(actor=request.user, start=form.cleaned_data['desde'], end=form.cleaned_data['hasta'])
    return render(request, 'historia/reportes/diario.html', _daily_context(form, report))


def _daily_context(form, report):
    context = {'form': form, 'report': report, 'daily_options': (*ADDITIONAL_OPTIONS, *PROCEDURE_OPTIONS)}
    if report:
        context['report_query'] = urlencode({'desde': report.start.isoformat(), 'hasta': report.end.isoformat()})
    return context


@capability_required('view_reports')
@require_safe
@xframe_options_sameorigin
def registro_diario_pdf_view(request):
    from .pdf_reports import daily_register_pdf
    data = request.GET if request.GET else {'fecha': timezone.localdate(timezone=REPORT_ZONE).isoformat()}
    form = FiltroReportesForm(data)
    if not form.is_valid():
        return render(request, 'historia/reportes/diario.html', _daily_context(form, None), status=400)
    start, end = form.cleaned_data['desde'], form.cleaned_data['hasta']
    try:
        content = daily_register_pdf(actor=request.user, start=start, end=end)
    except ValidationError as exc:
        form.add_error(None, exc)
        return render(request, 'historia/reportes/diario.html', _daily_context(form, None), status=422)
    response = HttpResponse(content, content_type='application/pdf')
    disposition = 'attachment' if request.GET.get('download') == '1' else 'inline'
    response['Content-Disposition'] = f'{disposition}; filename="FOR-SSS-02_{start.isoformat()}_{end.isoformat()}.pdf"'
    return response


@capability_required('view_reports')
@require_safe
def imprimir_registro_diario_view(request):
    from .pdf_reports import daily_register_pdf
    data = request.GET if request.GET else {'fecha': timezone.localdate(timezone=REPORT_ZONE).isoformat()}
    form = FiltroReportesForm(data)
    if not form.is_valid():
        return render(request, 'historia/reportes/diario.html', _daily_context(form, None), status=400)
    # Do not present print controls around a validation error inside an iframe.
    try:
        daily_register_pdf(actor=request.user, start=form.cleaned_data['desde'], end=form.cleaned_data['hasta'])
    except ValidationError as exc:
        form.add_error(None, exc)
        return render(request, 'historia/reportes/diario.html', _daily_context(form, None), status=422)
    query = urlencode({'desde': form.cleaned_data['desde'].isoformat(), 'hasta': form.cleaned_data['hasta'].isoformat()})
    return render(request, 'historia/reportes/imprimir.html', {'pdf_url': reverse('registro_diario_pdf')+'?'+query})


@capability_required('view_reports')
@require_safe
def reporte_pendientes_view(request):
    form = FiltroReportesForm(request.GET, allow_all=True)
    report = None
    if form.is_valid():
        report = pending_report(actor=request.user, start=form.cleaned_data['desde'], end=form.cleaned_data['hasta'])
    return render(request, 'historia/reportes/pendientes.html', {'form': form, 'report': report})
