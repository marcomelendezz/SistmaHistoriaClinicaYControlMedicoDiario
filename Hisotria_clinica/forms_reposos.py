from django import forms


class ReposoForm(forms.Form):
    motivo_reposo = forms.CharField(label='Motivo clínico del reposo', widget=forms.Textarea(attrs={'rows': 5, 'class': 'form-control'}))
    dias = forms.IntegerField(label='Cantidad de días', min_value=1, widget=forms.NumberInput(attrs={'class': 'form-control'}))
    fecha_inicio = forms.DateField(label='Fecha de inicio del reposo', widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'class': 'form-control'}))
    motivo_correccion = forms.CharField(label='Motivo de la nueva versión', widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}))
    motivo_cambio = forms.CharField(label='Motivo de modificación del borrador', widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}))
    expected_revision = forms.IntegerField(min_value=0, widget=forms.HiddenInput)

    def __init__(self, *args, editing=False, correction=False, **kwargs):
        super().__init__(*args, **kwargs)
        if not correction or editing:
            self.fields.pop('motivo_correccion')
        if not editing:
            self.fields.pop('motivo_cambio')
            self.fields.pop('expected_revision')


class AprobarReposoForm(forms.Form):
    expected_revision = forms.IntegerField(min_value=0, widget=forms.HiddenInput)
    review_token = forms.CharField(widget=forms.HiddenInput)
    confirmacion = forms.BooleanField(label='He revisado el paciente, el período, el motivo y la vista previa. Apruebo su emisión definitiva.')
