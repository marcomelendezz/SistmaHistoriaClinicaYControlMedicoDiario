from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from .models import Usuario

# formulario de registro

class RegistroForm(UserCreationForm):
    class Meta:
        model = Usuario
        fields = ['nombre', 'apellido', 'email', 'cargo']
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Aplicar clases de Bootstrap a todos los campos
        for name, field in self.fields.items():
            if name == 'cargo':
                field.widget.attrs['class'] = 'form-select'
            else:
                field.widget.attrs['class'] = 'form-control'
            
            # Placeholders opcionales
            field.widget.attrs['placeholder'] = f' {field.label.lower()}'

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