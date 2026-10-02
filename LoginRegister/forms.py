from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.core.validators import MinLengthValidator
from .models import Usuario
from django.contrib.auth.models import Group

# formulario de registro

User = get_user_model()

class RegistroForm(UserCreationForm):
    class Meta:
        model = Usuario
        fields = ['nombre', 'apellido', 'email', 'cargo']
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['password1'].min_length = 16
        self.fields['password1'].validators.append(MinLengthValidator(
            16,
            message='La contraseña es muy corta; debe tener al menos 16 caracteres.',
        ))
        self.fields['password1'].widget.attrs['minlength'] = 16

        # Aplicar clases de Bootstrap a todos los campos
        for name, field in self.fields.items():
            if name == 'cargo':
                field.widget.attrs['class'] = 'form-select form-select-md'
            else:
                field.widget.attrs['class'] = 'form-control form-control-md'
            
            # Placeholders opcionales
            field.widget.attrs['placeholder'] = f' {field.label.upper()}'

    def clean_password2(self):
        password1 = self.data.get(self.add_prefix('password1'), '').strip()
        password2 = self.cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError('Las contraseñas no coinciden.')
        return password2

    # funcion para asignar el grupo al usuario registrado
    def save(self, commit=True):
        user = super().save(commit=commit)       
        cargo_seleccionado = self.cleaned_data.get('cargo')

        if user and cargo_seleccionado:
            # Si 'cargo' es una relación ForeignKey a Group o retorna texto, convertimos a string
            nombre_grupo = str(cargo_seleccionado)
            
            try:
                # 3. Asignamos el grupo que coincide con el nombre del cargo
                grupo = Group.objects.get(name=nombre_grupo)
                user.groups.add(grupo)
            except Group.DoesNotExist:
                pass  # Si el grupo no está creado en el Admin aún, ignora el error

        return user

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