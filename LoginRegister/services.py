from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .access import require_capability
from .models import AccountAudit, Usuario


def account_snapshot(account):
    return {key: getattr(account, key) for key in (
        'requested_role', 'authorized_role', 'approval_status', 'is_active',
    )}


def accounts_for(actor):
    require_capability(actor, 'manage_accounts')
    return Usuario.objects.order_by('approval_status', 'email')


def account_audit_for(actor):
    require_capability(actor, 'manage_accounts')
    return AccountAudit.objects.select_related('actor', 'target')


@transaction.atomic
def review_account(*, actor, target_id, action, role='', reason=''):
    # Consistent locking order for administrative decisions.
    list(Usuario.objects.select_for_update().filter(
        authorized_role=Usuario.Role.ADMIN, approval_status=Usuario.Status.APPROVED,
        is_active=True,
    ).order_by('pk'))
    actor = require_capability(actor, 'manage_accounts')
    if actor.pk == int(target_id):
        raise PermissionDenied('No puedes modificar tu propia autorización administrativa.')
    reason = (reason or '').strip()
    target = Usuario.objects.select_for_update().get(pk=target_id)
    before = account_snapshot(target)
    if action == 'approve':
        if role not in Usuario.Role.values:
            raise ValidationError('Selecciona un rol autorizado válido.')
        target.authorized_role = role
        target.approval_status = Usuario.Status.APPROVED
        target.is_active = True
    elif action == 'reject':
        target.authorized_role = ''
        target.approval_status = Usuario.Status.REJECTED
    elif action == 'deactivate':
        target.is_active = False
    elif action == 'activate':
        if target.approval_status != Usuario.Status.APPROVED or target.authorized_role not in Usuario.Role.values:
            raise ValidationError('Primero debes aprobar la cuenta y asignarle un rol.')
        target.is_active = True
    else:
        raise ValidationError('Operación no válida.')
    # The active administrator actor cannot change itself, preserving access.
    target.reviewed_by = actor
    target.reviewed_at = timezone.now()
    target.review_reason = reason.strip()
    target.save(update_fields=['authorized_role', 'approval_status', 'is_active', 'reviewed_by', 'reviewed_at', 'review_reason'])
    AccountAudit.objects.create(actor=actor, target=target, action=action,
                               reason=reason.strip(), before=before, after=account_snapshot(target))
    return target
