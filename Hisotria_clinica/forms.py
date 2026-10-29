from django import forms
from django.utils import timezone
from .models import Atencion, Estudiante, HistoriaClinica
from .services import validate_new_identity
from LoginRegister.models import Usuario
from .daily_options import OPTION_CODES, OPTION_GROUPS


class EstudianteForm(forms.ModelForm):
    class Meta:
        model = Estudiante
        fields = ['nombre', 'apellido', 'cedula', 'tipo_paciente', 'fecha_nacimiento', 'sexo',
                  'lugar_nacimiento', 'edo_civil', 'direccion', 'telefono', 'contacto_emergencia',
                  'parentesco_emergencia', 'telefono_emergencia', 'pnf', 'cargo_laboral']
        labels = {'nombre': 'Nombres', 'apellido': 'Apellidos', 'cedula': 'Cédula',
                  'tipo_paciente': 'Tipo de paciente', 'edo_civil': 'Estado civil',
                  'fecha_nacimiento': 'Fecha de nacimiento',
                  'direccion': 'Dirección', 'telefono': 'Teléfono', 'contacto_emergencia': 'Contacto de emergencia'}
        widgets = {
            'sexo': forms.Select(choices=[('', 'Seleccione...'), ('Masculino', 'Masculino'), ('Femenino', 'Femenino')]),
            'fecha_nacimiento': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tipo_paciente'].required = True
        self.fields['cedula'].required = True
        if self.instance.pk:
            self.fields['cedula'].disabled = True
            self.fields['cedula'].required = bool(self.instance.cedula)
            self.fields['cedula'].help_text = 'Identificación histórica conservada.'
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-select' if isinstance(field.widget, forms.Select) else 'form-control'

    def clean_cedula(self):
        if self.instance.pk:
            return self.instance.cedula
        return validate_new_identity(self.cleaned_data['cedula'])

    def clean_fecha_nacimiento(self):
        birth = self.cleaned_data['fecha_nacimiento']
        if (not self.instance.pk or birth != self.instance.fecha_nacimiento) and birth > timezone.localdate():
            raise forms.ValidationError('La fecha de nacimiento no puede estar en el futuro.')
        return birth

    def clean(self):
        data = super().clean()
        category = data.get('tipo_paciente')
        if category != Estudiante.Tipo.ESTUDIANTE:
            data.pop('pnf', None)
        if category not in [Estudiante.Tipo.PROFESOR, Estudiante.Tipo.OBRERO_TECNICO, Estudiante.Tipo.ADMINISTRATIVO]:
            data.pop('cargo_laboral', None)
        return data


class HistoriaClinicaForm(forms.ModelForm):
    class Meta:
        model = HistoriaClinica
        fields = ['fecha_consulta', 'motivo_consulta', 'enfermedad_actual', 'diagnostico_provisional',
                  'diagnostico', 'tratamiento', 'observaciones', *OPTION_CODES]
        labels = {'fecha_consulta': 'Fecha de consulta', 'motivo_consulta': 'Motivo de consulta',
                  'diagnostico': 'Diagnóstico', 'tratamiento': 'Tratamiento', 'observaciones': 'Observaciones'}
        widgets = {
            'fecha_consulta': forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'}),
            'motivo_consulta': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'enfermedad_actual': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'diagnostico_provisional': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'diagnostico': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'tratamiento': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'observaciones': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for code in ['enfermedad_actual', 'diagnostico_provisional']:
            self.fields[code].help_text = 'Necesario para emitir el PDF FOR-SSS-04. No se completa desde otros campos.'
        for _, options in OPTION_GROUPS:
            for code, label in options:
                self.fields[code] = forms.BooleanField(label=label, required=False,
                    widget=forms.CheckboxInput(attrs={'class': 'daily-option'}))

    @property
    def text_fields(self):
        return [field for field in self.visible_fields() if field.name not in OPTION_CODES]

    @property
    def daily_option_groups(self):
        return [(title, [self[code] for code, _ in options]) for title, options in OPTION_GROUPS]


class LlegadaForm(forms.Form):
    arrival = forms.DateTimeField(label='Fecha y hora de llegada',
        input_formats=['%Y-%m-%dT%H:%M', '%Y-%m-%dT%H:%M:%S'],
        widget=forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local', 'class': 'form-control'}))
    reason = forms.CharField(label='Motivo de visita', max_length=4000,
        widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}))
    shift = forms.CharField(label='Turno (opcional)', max_length=50, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}))
    nurse = forms.ModelChoiceField(label='Enfermera responsable (opcional)', required=False,
        queryset=Usuario.objects.filter(is_active=True, approval_status='aprobado', authorized_role='enfermera').order_by('apellido', 'nombre', 'pk'),
        empty_label='Sin registrar', widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Selecciona solo si está confirmada. No se asigna automáticamente.')


class CambioEstadoForm(forms.Form):
    target = forms.ChoiceField(choices=[('en_atencion', 'En atención'), ('cancelado', 'Cancelado / no atendido')])
    expected_version = forms.IntegerField(min_value=0, widget=forms.HiddenInput)


class CorreccionClinicaForm(HistoriaClinicaForm):
    reason = forms.CharField(label='Motivo de corrección (obligatorio)', max_length=4000,
        widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}))
    expected_version = forms.IntegerField(min_value=0, widget=forms.HiddenInput)


class FiltroAtencionesForm(forms.Form):
    fecha = forms.DateField(label='Fecha', required=False, widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    estado = forms.ChoiceField(label='Estado', required=False, choices=[('', 'Todos'), *Atencion.Estado.choices], widget=forms.Select(attrs={'class': 'form-select'}))
    q = forms.CharField(label='Cédula o nombre', required=False, max_length=150, widget=forms.TextInput(attrs={'class': 'form-control'}))


class FiltroReportesForm(forms.Form):
    fecha = forms.DateField(label='Una fecha', required=False,
        widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'class': 'form-control'}))
    desde = forms.DateField(label='Desde', required=False,
        widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'class': 'form-control'}))
    hasta = forms.DateField(label='Hasta', required=False,
        widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'class': 'form-control'}))

    def __init__(self, *args, allow_all=False, **kwargs):
        self.allow_all = allow_all
        super().__init__(*args, **kwargs)

    def clean(self):
        from .reports import validate_period
        data = super().clean()
        if self.errors:
            return data
        single, start, end = data.get('fecha'), data.get('desde'), data.get('hasta')
        if single and (start or end):
            raise forms.ValidationError('Usa una fecha o un rango, sin combinar ambos filtros.')
        if single:
            start = end = single
        validate_period(start, end, allow_all=self.allow_all)
        data['desde'], data['hasta'] = start, end
        return data
