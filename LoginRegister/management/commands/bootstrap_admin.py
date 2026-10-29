from getpass import getpass

from axes.utils import reset
from axes.models import AccessAttempt
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.hashers import check_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import connection, transaction
from django.utils import timezone

from LoginRegister.models import AccountAudit, Usuario
from LoginRegister.services import account_snapshot


class Command(BaseCommand):
    help = 'Crea o designa un administrador institucional local, verificando su contraseña sin otorgar facultades médicas.'

    def add_arguments(self, parser):
        parser.add_argument('--email', required=True)
        parser.add_argument('--nombre', default='')
        parser.add_argument('--apellido', default='')
        group = parser.add_mutually_exclusive_group()
        group.add_argument('--designate-existing', action='store_true')
        group.add_argument('--verify', action='store_true')

    @transaction.atomic
    def handle(self, *args, **options):
        tables = connection.introspection.table_names()
        if Usuario._meta.db_table not in tables or AccountAudit._meta.db_table not in tables:
            raise CommandError('Primero aplica el esquema: migrate LoginRegister 0003. Consulta docs/FASE1.md.')
        email = options['email'].strip()
        try:
            validate_email(email)
        except ValidationError as exc:
            raise CommandError('Indica un correo válido.') from exc
        matches = Usuario.objects.select_for_update().filter(email__iexact=email)
        if matches.count() > 1:
            raise CommandError('Hay correos antiguos equivalentes. Revísalos antes de designar un administrador.')
        account = matches.first()
        if options['verify']:
            if not account or not account.is_active or account.approval_status != Usuario.Status.APPROVED or account.authorized_role != Usuario.Role.ADMIN:
                raise CommandError('La cuenta debe ser un administrador activo y aprobado.')
        elif options['designate_existing']:
            if account is None:
                raise CommandError('No existe esa cuenta. Omite --designate-existing para crear una nueva.')
        elif account:
            raise CommandError('La cuenta existe. Usa --designate-existing o --verify; nunca se reemplaza su contraseña.')
        else:
            if not options['nombre'].strip() or not options['apellido'].strip():
                raise CommandError('Para crear una cuenta indica --nombre y --apellido.')
            account = Usuario(email=email, nombre=options['nombre'].strip(), apellido=options['apellido'].strip(), cargo='')

        before = account_snapshot(account) if account.pk else {}
        password = getpass('Contraseña actual: ' if account.pk else 'Nueva contraseña (mínimo 16 caracteres): ')
        if account.pk:
            # Model.check_password may persist an upgraded hash. Verification must
            # preserve the existing hash as well as the password itself.
            if not check_password(password, account.password):
                raise CommandError('No fue posible verificar la contraseña; no se hicieron cambios.')
        else:
            if password != getpass('Confirmar contraseña: '):
                raise CommandError('Las contraseñas no coinciden.')
            try:
                validate_password(password, account)
            except ValidationError as exc:
                raise CommandError('; '.join(exc.messages)) from exc
            account.set_password(password)
        if not options['verify']:
            account.authorized_role = Usuario.Role.ADMIN
            account.approval_status = Usuario.Status.APPROVED
            account.is_active = True
            account.reviewed_at = timezone.now()
            account.review_reason = 'Designación administrativa explícita mediante consola local.'
            # Existing passwords, technical flags and historical cargo are preserved.
            account.save()
            account.reviewed_by = account
            account.save(update_fields=['reviewed_by'])
        # The initial schema stage need not have installed Axes tables yet.
        if AccessAttempt._meta.db_table in connection.introspection.table_names():
            reset(username=account.email)
        AccountAudit.objects.create(actor=account, target=account, action='bootstrap_verified',
            reason='Administrador verificado por operador con acceso a consola y contraseña de la cuenta.',
            before=before, after=account_snapshot(account))
        self.stdout.write(self.style.SUCCESS('Administrador verificado. Puede gestionar /cuentas/; no se otorgaron permisos médicos.'))
