from django.shortcuts import render
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.models import Group
from .forms import CustomLoginForm, RegistroForm

# Create your views here.

def login_view(request):
    if request.method == 'POST':
        form = CustomLoginForm(data=request.POST)
        if form.is_valid():
            # ... tu lógica de inicio de sesión
            pass
    else:
        form = CustomLoginForm() # Usa la clase con los atributos de Bootstrap
        
    return render(request, 'LoginRegister/login.html', {'form': form})


def register_view(request):
    if request.method == 'POST':
        form = RegistroForm(request.POST)
        if form.is_valid():
            form.save()
            return render(request, 'LoginRegister/register.html', {
                'form': RegistroForm(),
                'registro_exitoso': True,
            })
    else:
        form = RegistroForm()

    return render(request, 'LoginRegister/register.html', {'form': form})