from django.shortcuts import redirect, render
from .forms import EstudianteForm, HistoriaClinicaForm
from .models import HistoriaClinica


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


def lista_historia_view(request):
    historias = HistoriaClinica.objects.select_related('estudiante').all().order_by('-fecha_consulta')
    return render(request, 'historia/lista_historia.html', {'historias': historias})