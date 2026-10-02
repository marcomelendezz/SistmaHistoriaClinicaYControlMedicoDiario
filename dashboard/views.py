from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required
from .forms import PerfilForm

# Create your views here.

@login_required
def dashboard_view(request):
    return render(request, 'dashboard/dashboard.html')

@login_required(login_url='login')
def mi_perfil_view(request):
    return render(request, 'dashboard/mi_perfil.html', {'perfil': request.user})

@login_required(login_url='login')
def editar_perfil_view(request):
    if request.method == 'POST':
        form = PerfilForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            return redirect('mi_perfil')
    else:
        form = PerfilForm(instance=request.user)

    return render(request, 'dashboard/editar_perfil.html', {'form': form})