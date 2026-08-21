from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from .models import Usuario

# formulario de registro

class RegistroForm(UserCreationForm):
    class Meta:
        model = Usuario
        fields = ['nombre', 'apellido', 'email', 'cargo', 'password1', 'password2']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Aplicar clases de Bootstrap a todos los campos
        for name, field in self.fields.items():
            if name == 'cargo':
                field.widget.attrs['class'] = 'form-select'
            else:
                field.widget.attrs['class'] = 'form-control'
            
            # Placeholders opcionales
            field.widget.attrs['placeholder'] = f'Ingrese {field.label.lower()}'

# formulario de inicio de sesión

class CustomLoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({
            'class': 'form-control form-control-md',
            'placeholder': 'CORREO ELECTRONICO'
        })
        self.fields['password'].widget.attrs.update({
            'class': 'form-control form-control-md',
            'placeholder': 'CONTRASEÑA'
        })