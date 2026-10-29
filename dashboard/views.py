from django.shortcuts import redirect, render
from LoginRegister.access import capability_required
from .forms import PerfilForm
from django.utils import timezone
from Hisotria_clinica.services import attentions_for

# Create your views here.

@capability_required('read_clinical')
def dashboard_view(request):
    attentions = attentions_for(request.user)
    return render(request, 'dashboard/dashboard.html', {
        'pending': attentions.filter(estado='pendiente').count(),
        'in_progress': attentions.filter(estado='en_atencion').count(),
        'completed_today': attentions.filter(actualizada_en__date=timezone.localdate(), estado='atendido', historia__isnull=False).count(),
    })

@capability_required('read_clinical')
def mi_perfil_view(request):
    return render(request, 'dashboard/mi_perfil.html', {'perfil': request.user})

@capability_required('read_clinical')
def editar_perfil_view(request):
    if request.method == 'POST':
        form = PerfilForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            return redirect('mi_perfil')
    else:
        form = PerfilForm(instance=request.user)

    return render(request, 'dashboard/editar_perfil.html', {'form': form})
