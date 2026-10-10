from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.models import Group
from .forms import CustomLoginForm, RegistroForm
from django.contrib import messages
from django.contrib.auth.views import PasswordResetConfirmView
from axes.helpers import reset_user_lockout

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

class CustomPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = 'accounts/password_reset_confirm.html'
    
    def form_valid(self, form):
        # 1. Guarda la nueva contraseña usando el comportamiento normal de Django
        response = super().form_valid(form)
        
        # 2. Obtiene el usuario que acaba de cambiar la contraseña
        user = form.user
        
        # 3. Desbloquea al usuario en django-axes usando su nombre de usuario
        reset_user_lockout(request=self.request, username=user.username)
        
        return response