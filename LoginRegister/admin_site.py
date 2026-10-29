from django.contrib.admin import AdminSite
from django.contrib.admin.forms import AdminAuthenticationForm
from django.core.exceptions import ValidationError
from .access import has_capability


class InstitutionalAdminForm(AdminAuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not has_capability(user, 'manage_accounts'):
            raise ValidationError('Se requiere autorización administrativa institucional.')


class AccountAdminSite(AdminSite):
    login_form = InstitutionalAdminForm
    def has_permission(self, request):
        return request.user.is_staff and has_capability(request.user, 'manage_accounts')
