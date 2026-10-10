from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.models import Group
from .forms import CustomLoginForm, RegistroForm
from django.contrib import messages

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
            messages.success(request, 'Registrado correctamente. Ya puedes iniciar sesión.')
            return redirect('login')
    else:
        form = RegistroForm()

    return render(request, 'LoginRegister/register.html', {'form': form})

def blocked_view(request):
    return render(request, 'LoginRegister/accounts/bloqueo.html')