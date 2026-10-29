from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST, require_safe, require_http_methods

from LoginRegister.access import capability_required
from .forms_reposos import AprobarReposoForm, ReposoForm
from .models import ConstanciaReposo
from .reposos import (approve_reposo, create_reposo_draft, issued_reposo_pdf,
                     review_reposo, update_reposo_draft)
from .reports import REPORT_ZONE
from .services import histories_for


def _owned(request, record):
    if record.historia.medico_id != request.user.pk:
        raise PermissionDenied('Solo el médico responsable de la consulta puede modificar o revisar este borrador.')


def _error(request, record, errors):
    return render(request, 'historia/reposos/error.html', {'reposo': record, 'errors': errors}, status=422)


@capability_required('manage_reposo')
@require_http_methods(['GET', 'POST'])
def nuevo_reposo_view(request, history_id):
    history = get_object_or_404(histories_for(request.user), pk=history_id)
    if history.medico_id != request.user.pk:
        raise PermissionDenied('Solo el médico responsable de esta consulta puede preparar el reposo.')
    previous = None
    previous_id = request.GET.get('anterior')
    if previous_id:
        try:
            previous_id = int(previous_id)
        except (ValueError, TypeError) as exc:
            raise Http404('Versión anterior no válida.') from exc
        previous = get_object_or_404(ConstanciaReposo, pk=previous_id, historia=history, estado='emitida')
    initial = {'fecha_inicio': timezone.localdate(timezone=REPORT_ZONE)}
    if previous:
        initial.update(motivo_reposo=previous.motivo_reposo, dias=previous.dias, fecha_inicio=previous.fecha_inicio)
    form = ReposoForm(request.POST if request.method == 'POST' else None, initial=initial, correction=bool(previous))
    if request.method == 'POST' and form.is_valid():
        data = dict(form.cleaned_data)
        correction = data.pop('motivo_correccion', '')
        try:
            record = create_reposo_draft(actor=request.user, history_id=history.pk, data=data,
                                        previous_id=previous.pk if previous else None, correction_reason=correction)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, 'Borrador guardado. Revisa el documento antes de aprobarlo.')
            return redirect('detalle_reposo', pk=record.pk)
    return render(request, 'historia/reposos/form.html', {'form': form, 'historia': history, 'previous': previous})


@capability_required('manage_reposo')
@require_http_methods(['GET', 'POST'])
def editar_reposo_view(request, pk):
    record = get_object_or_404(ConstanciaReposo.objects.select_related('historia__estudiante').defer('pdf'), pk=pk)
    _owned(request, record)
    if record.estado != 'borrador':
        return _error(request, record, ['Una constancia emitida no se edita. Prepara una nueva versión.'])
    initial = {key: getattr(record, key) for key in ['motivo_reposo', 'dias', 'fecha_inicio']}
    initial['expected_revision'] = record.revision
    form = ReposoForm(request.POST if request.method == 'POST' else None, initial=initial, editing=True)
    if request.method == 'POST' and form.is_valid():
        data = dict(form.cleaned_data)
        reason = data.pop('motivo_cambio')
        revision = data.pop('expected_revision')
        try:
            update_reposo_draft(actor=request.user, reposo_id=pk, data=data, expected_revision=revision, reason=reason)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            return redirect('detalle_reposo', pk=pk)
    return render(request, 'historia/reposos/form.html', {'form': form, 'historia': record.historia, 'reposo': record})


@capability_required('export_clinical')
@require_safe
def detalle_reposo_view(request, pk):
    record = get_object_or_404(ConstanciaReposo.objects.select_related('historia').defer('pdf'), pk=pk)
    context = {'reposo': record}
    if record.estado == 'borrador':
        _owned(request, record)
        try:
            record, snapshot, _, token = review_reposo(actor=request.user, reposo_id=pk)
        except ValidationError as exc:
            return _error(request, record, exc.messages)
        context.update(snapshot=snapshot, approval_form=AprobarReposoForm(initial={
            'expected_revision': record.revision, 'review_token': token}))
    else:
        context['snapshot'] = record.datos_emitidos
        following = ConstanciaReposo.objects.filter(anterior=record).only('pk', 'estado', 'numero_version').first()
        context['following'] = following if following and (following.estado == 'emitida' or record.historia.medico_id == request.user.pk) else None
        context['can_create_version'] = record.historia.medico_id == request.user.pk and following is None
    return render(request, 'historia/reposos/detalle.html', context)


@capability_required('manage_reposo')
@require_POST
def aprobar_reposo_view(request, pk):
    record = get_object_or_404(ConstanciaReposo.objects.select_related('historia'), pk=pk)
    _owned(request, record)
    form = AprobarReposoForm(request.POST)
    if not form.is_valid():
        return _error(request, record, ['Confirma la revisión y utiliza una vista previa vigente.'])
    try:
        approve_reposo(actor=request.user, reposo_id=pk, expected_revision=form.cleaned_data['expected_revision'],
                       review_token=form.cleaned_data['review_token'], confirmed=form.cleaned_data['confirmacion'])
    except ValidationError as exc:
        return _error(request, record, exc.messages)
    messages.success(request, 'Constancia aprobada. Se conservó su PDF definitivo e inmutable.')
    return redirect('detalle_reposo', pk=pk)


@capability_required('manage_reposo')
@require_safe
@xframe_options_sameorigin
def preview_reposo_view(request, pk):
    record = get_object_or_404(ConstanciaReposo.objects.select_related('historia'), pk=pk)
    _owned(request, record)
    try:
        _, _, content, _ = review_reposo(actor=request.user, reposo_id=pk)
    except ValidationError as exc:
        return _error(request, record, exc.messages)
    response = HttpResponse(content, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="BORRADOR_FOR-SSS-07_{pk}.pdf"'
    return response


@capability_required('export_clinical')
@require_safe
@xframe_options_sameorigin
def reposo_pdf_view(request, pk):
    record = get_object_or_404(ConstanciaReposo.objects.defer('pdf', 'datos_emitidos'), pk=pk)
    try:
        record, content = issued_reposo_pdf(actor=request.user, reposo_id=pk)
    except ValidationError as exc:
        return _error(request, record, exc.messages)
    response = HttpResponse(content, content_type='application/pdf')
    disposition = 'attachment' if request.GET.get('download') == '1' else 'inline'
    response['Content-Disposition'] = f'{disposition}; filename="FOR-SSS-07_{pk}_v{record.numero_version}.pdf"'
    return response


@capability_required('export_clinical')
@require_safe
def imprimir_reposo_view(request, pk):
    record = get_object_or_404(ConstanciaReposo.objects.defer('pdf', 'datos_emitidos'), pk=pk)
    try:
        issued_reposo_pdf(actor=request.user, reposo_id=pk)
    except ValidationError as exc:
        return _error(request, record, exc.messages)
    return render(request, 'historia/reposos/imprimir.html', {'reposo': record, 'pdf_url': reverse('reposo_pdf', args=[pk])})
