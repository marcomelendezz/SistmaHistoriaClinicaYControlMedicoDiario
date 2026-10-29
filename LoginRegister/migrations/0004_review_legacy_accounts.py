from django.db import migrations


def queue_legacy_accounts(apps, schema_editor):
    User = apps.get_model('LoginRegister', 'Usuario')
    Audit = apps.get_model('LoginRegister', 'AccountAudit')
    database = schema_editor.connection.alias
    legacy = User.objects.using(database).filter(approval_status='legacy')
    if not legacy.exists():
        return
    verified_ids = Audit.objects.using(database).filter(action='bootstrap_verified').values('target_id')
    administrator = User.objects.using(database).filter(
        pk__in=verified_ids, authorized_role='administrador',
        approval_status='aprobado', is_active=True,
    ).order_by('pk').first()
    if administrator is None:
        raise RuntimeError(
            'Se requiere un administrador verificado. Aplique LoginRegister 0003, '
            'ejecute bootstrap_admin y después reanude migrate. No se modificaron las cuentas antiguas.'
        )
    mapping = {'Medico': 'medico', 'medico': 'medico', 'Enfermero/a': 'enfermera', 'enfermero': 'enfermera'}
    for account in legacy.iterator():
        before = {'approval_status': account.approval_status, 'requested_role': account.requested_role, 'authorized_role': account.authorized_role}
        # Existing cargo/password/pk/groups/active flags remain unchanged.
        account.requested_role = mapping.get(account.cargo, '')
        account.authorized_role = ''
        account.approval_status = 'pendiente'
        account.save(using=database, update_fields=['requested_role', 'authorized_role', 'approval_status'])
        after = {'approval_status': account.approval_status, 'requested_role': account.requested_role, 'authorized_role': account.authorized_role}
        Audit.objects.using(database).create(actor_id=administrator.pk, target_id=account.pk,
            action='legacy_review_pending', reason='Cuenta antigua pendiente de verificación institucional.', before=before, after=after)


def restore_unreviewed_accounts(apps, schema_editor):
    User = apps.get_model('LoginRegister', 'Usuario')
    Audit = apps.get_model('LoginRegister', 'AccountAudit')
    database = schema_editor.connection.alias
    for event in Audit.objects.using(database).filter(action='legacy_review_pending').order_by('pk').iterator():
        account = User.objects.using(database).filter(pk=event.target_id, reviewed_at__isnull=True, **event.after).first()
        if account:
            User.objects.using(database).filter(pk=account.pk).update(**event.before)
            Audit.objects.using(database).create(actor_id=event.actor_id, target_id=event.target_id,
                action='legacy_review_rollback', reason='Reversión de la cola sin revertir revisiones posteriores.', before=event.after, after=event.before)


class Migration(migrations.Migration):
    dependencies = [('LoginRegister', '0003_account_approval_schema')]
    operations = [migrations.RunPython(queue_legacy_accounts, restore_unreviewed_accounts)]
