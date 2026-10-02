from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from .forms import EstudianteForm, HistoriaClinicaForm
from .models import Estudiante, HistoriaClinica
from django.contrib.auth.decorators import login_required

@login_required
def registro_historia_view(request): 
    estudiante_form = EstudianteForm(request.POST or None)
    historia_form = HistoriaClinicaForm(request.POST or None)

    if request.method == 'POST':
        if estudiante_form.is_valid() and historia_form.is_valid():
            estudiante = estudiante_form.save()
            historia = historia_form.save(commit=False)
            historia.estudiante = estudiante
            historia.save()
            return redirect('registro_historia')

    return render(
        request,
        'historia/historia.html',
        {
            'estudiante_form': estudiante_form,
            'historia_form': historia_form,
        }
    )

@login_required
def nueva_consulta_view(request):
    query = request.GET.get('q', '').strip()
    estudiantes = Estudiante.objects.all().order_by('apellido', 'nombre')

    if query:
        estudiantes = estudiantes.filter(
            Q(nombre__icontains=query) |
            Q(apellido__icontains=query) |
            Q(cedula__icontains=query)
        )

    selected_estudiante = None
    estudiante_id = request.POST.get('estudiante') or request.GET.get('estudiante')
    if estudiante_id:
        selected_estudiante = get_object_or_404(Estudiante, pk=estudiante_id)

    historia_form = HistoriaClinicaForm(request.POST or None)

    if request.method == 'POST':
        estudiante_id = request.POST.get('estudiante')
        if estudiante_id:
            selected_estudiante = get_object_or_404(Estudiante, pk=estudiante_id)

        if estudiante_id and historia_form.is_valid():
            historia = historia_form.save(commit=False)
            historia.estudiante = selected_estudiante
            historia.save()
            return redirect('lista_historia')

    return render(
        request,
        'historia/nueva_consulta.html',
        {
            'historia_form': historia_form,
            'estudiantes': estudiantes,
            'selected_estudiante': selected_estudiante,
            'query': query,
        }
    )

@login_required
def lista_historia_view(request):
    query = request.GET.get('q', '').strip()
    estudiantes = Estudiante.objects.all().order_by('apellido', 'nombre')
    selected_estudiante = None
    estudiante_id = request.GET.get('estudiante')

    if estudiante_id:
        selected_estudiante = get_object_or_404(Estudiante, pk=estudiante_id)
    elif query:
        estudiantes_por_cedula = Estudiante.objects.filter(cedula__icontains=query)

        if estudiantes_por_cedula.count() == 1:
            selected_estudiante = estudiantes_por_cedula.first()
        else:
            estudiantes = estudiantes.filter(
                Q(nombre__icontains=query) |
                Q(apellido__icontains=query) |
                Q(cedula__icontains=query)
            )

    if not selected_estudiante and query and not estudiante_id:
        estudiantes = estudiantes.filter(
            Q(nombre__icontains=query) |
            Q(apellido__icontains=query) |
            Q(cedula__icontains=query)
        )

    historias = []
    if selected_estudiante:
        historias = HistoriaClinica.objects.filter(estudiante=selected_estudiante).select_related('estudiante').order_by('-fecha_consulta')

    return render(
        request,
        'historia/lista_historia.html',
        {
            'historias': historias,
            'estudiantes': estudiantes,
            'selected_estudiante': selected_estudiante,
            'query': query,
        }
    )