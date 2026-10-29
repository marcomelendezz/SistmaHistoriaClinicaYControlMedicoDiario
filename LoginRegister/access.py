from functools import wraps

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.views.decorators.cache import never_cache


CAPABILITIES = {
    'read_clinical': {'medico', 'enfermera', 'administrador'},
    'write_clinical': {'medico'},
    'export_clinical': {'medico'},
    'manage_reposo': {'medico'},
    'manage_patients': {'medico', 'enfermera'},
    'manage_attention': {'medico', 'enfermera'},
    'view_reports': {'medico', 'enfermera'},
    'manage_accounts': {'administrador'},
}


def current_account(actor):
    if not getattr(actor, 'is_authenticated', False) or not actor.pk:
        raise PermissionDenied('Debes iniciar sesión.')
    account = get_user_model().objects.filter(pk=actor.pk).first()
    if not account or not account.is_active or account.approval_status != 'aprobado':
        raise PermissionDenied('La cuenta necesita aprobación administrativa y debe estar activa.')
    return account


def require_capability(actor, capability):
    account = current_account(actor)
    if account.authorized_role not in CAPABILITIES.get(capability, set()):
        raise PermissionDenied('Tu cuenta no tiene autorización para realizar esta operación.')
    return account


def has_capability(actor, capability):
    try:
        require_capability(actor, capability)
        return True
    except PermissionDenied:
        return False


def capability_required(capability):
    def decorator(view):
        @never_cache
        @login_required
        @wraps(view)
        def guarded(request, *args, **kwargs):
            require_capability(request.user, capability)
            return view(request, *args, **kwargs)
        return guarded
    return decorator
