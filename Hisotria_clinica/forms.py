from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from .models import Estudiante, HistoriaClinica
User = get_user_model()

class EstudianteForm(forms.ModelForm):
    class Meta:
        model = Estudiante
        fields = ['nombre', 'apellido', 'edad', 'edo_civil', 'sexo', 'direccion', 'contacto_emergencia', 'telefono', 'fecha_nacimiento']

class HistoriaClinicaForm(forms.ModelForm):
    class Meta:
        model = HistoriaClinica
        fields = ['estudiante', 'fecha_consulta', 'motivo_consulta', 'diagnostico', 'tratamiento', 'observaciones']