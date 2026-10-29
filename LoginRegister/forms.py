from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.exceptions import ValidationError
from .models import Usuario


class RegistroForm(UserCreationForm):
    error_messages = {**UserCreationForm.error_messages, 'password_mismatch': 'Las contraseñas no coinciden.'}
    requested_role = forms.ChoiceField(label='Rol solicitado', choices=[
        (Usuario.Role.DOCTOR, 'Médico'), (Usuario.Role.NURSE, 'Enfermera'),
    ])

    class Meta:
        model = Usuario
        fields = ['nombre', 'apellido', 'email', 'requested_role']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].min_length = 16
        self.fields['password1'].widget.attrs['minlength'] = 16
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-select' if isinstance(field.widget, forms.Select) else 'form-control'

    def clean_email(self):
        email = self.cleaned_data['email'].strip()
        if Usuario.objects.filter(email__iexact=email).exists():
            raise ValidationError('Ya existe una cuenta con este correo electrónico.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.authorized_role = ''
        user.approval_status = Usuario.Status.PENDING
        user.is_staff = False
        user.is_superuser = False
        user.cargo = 'Medico' if user.requested_role == Usuario.Role.DOCTOR else 'Enfermero/a'
        if commit:
            user.save()
        return user


class CustomLoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({'class': 'form-control', 'placeholder': 'CORREO ELECTRÓNICO'})
        self.fields['password'].widget.attrs.update({'class': 'form-control', 'placeholder': 'CONTRASEÑA'})

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if user.approval_status != Usuario.Status.APPROVED or user.authorized_role not in Usuario.Role.values:
            raise ValidationError('Tu cuenta está pendiente de aprobación o no está autorizada. Contacta al administrador.', code='unapproved')


class AccountReviewForm(forms.Form):
    action = forms.ChoiceField(label='Acción', choices=[
        ('approve', 'Aprobar / asignar rol'), ('reject', 'Rechazar'),
        ('deactivate', 'Desactivar'), ('activate', 'Activar cuenta aprobada'),
    ])
    role = forms.ChoiceField(label='Rol autorizado', required=False, choices=[('', 'Seleccione...'), *Usuario.Role.choices])
    reason = forms.CharField(label='Observación (opcional)', required=False,
        widget=forms.Textarea(attrs={'rows': 2}), max_length=2000,
        help_text='No es necesaria para aprobar, asignar rol o rechazar una solicitud.')

    def clean(self):
        data = super().clean()
        if data.get('action') == 'approve' and not data.get('role'):
            self.add_error('role', 'Selecciona el rol autorizado.')
        return data
