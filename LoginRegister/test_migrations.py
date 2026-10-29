from io import StringIO
from unittest.mock import patch

from django.contrib.auth.hashers import make_password
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class LegacyAccountMigrationTests(TransactionTestCase):
    """Exercise the real staged upgrade with synthetic rows, including rollback."""
    def test_administrator_can_be_created_before_axes_schema_exists(self):
        executor = MigrationExecutor(connection)
        try:
            executor.migrate([('LoginRegister', '0003_account_approval_schema'), ('axes', None)])
            self.assertNotIn('axes_accessattempt', connection.introspection.table_names())
            password = 'Synthetic-Initial-Password-2026!'
            with patch('LoginRegister.management.commands.bootstrap_admin.getpass', side_effect=[password, password]):
                call_command('bootstrap_admin', email='initial@example.invalid', nombre='Administrador', apellido='Ficticio', stdout=StringIO())
            from .models import Usuario
            admin = Usuario.objects.get(email='initial@example.invalid')
            self.assertEqual(admin.authorized_role, 'administrador')
            self.assertEqual(admin.approval_status, 'aprobado')
            self.assertTrue(admin.check_password(password))
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())

    def test_guard_bootstrap_preservation_and_safe_reverse(self):
        executor = MigrationExecutor(connection)
        executor.migrate([('LoginRegister', '0002_alter_usuario_cargo')])
        old_apps = executor.loader.project_state([('LoginRegister', '0002_alter_usuario_cargo')]).apps
        User = old_apps.get_model('LoginRegister', 'Usuario')
        password = 'Synthetic-Migration-Password-2026!'
        encoded = make_password(password)
        old = User.objects.create(email='legacy@example.invalid', password=encoded, cargo='Medico', nombre='Médico', apellido='Ficticio')
        ambiguous = User.objects.create(email='ambiguous@example.invalid', password=encoded, cargo='Valor ambiguo', is_staff=True, is_superuser=True)
        group = old_apps.get_model('auth', 'Group').objects.create(name='Grupo histórico ficticio')
        old.groups.add(group)
        # Clinical fixtures are retained byte-for-byte by the account migrations.
        from Hisotria_clinica.models import Estudiante, HistoriaClinica
        patient = Estudiante.objects.create(nombre='Paciente', apellido='Ficticio', cedula='SYNTHETIC-MIG', edad=26, edo_civil='Soltero', sexo='Masculino', direccion='Ficticia', contacto_emergencia='Ficticio', telefono='0000', fecha_nacimiento='2000-01-01')
        history = HistoriaClinica.objects.create(estudiante=patient, fecha_consulta='2026-10-27', motivo_consulta='Ficticio', diagnostico='Ficticio', tratamiento='Ficticio')
        clinical_before = list(HistoriaClinica.objects.values())
        try:
            executor = MigrationExecutor(connection)
            executor.migrate([('LoginRegister', '0003_account_approval_schema')])
            from .models import Usuario, AccountAudit
            self.assertEqual(Usuario.objects.get(pk=old.pk).approval_status, 'legacy')
            with self.assertRaisesRegex(RuntimeError, 'administrador verificado'):
                MigrationExecutor(connection).migrate([('LoginRegister', '0004_review_legacy_accounts')])
            self.assertEqual(Usuario.objects.get(pk=old.pk).approval_status, 'legacy')
            with patch('LoginRegister.management.commands.bootstrap_admin.getpass', side_effect=[password, password]):
                call_command('bootstrap_admin', email='initial@example.invalid', nombre='Administrador', apellido='Ficticio', stdout=StringIO())
            MigrationExecutor(connection).migrate([('LoginRegister', '0004_review_legacy_accounts')])
            migrated = Usuario.objects.get(pk=old.pk)
            self.assertEqual((migrated.password, migrated.cargo, migrated.requested_role, migrated.authorized_role, migrated.approval_status),
                             (encoded, 'Medico', 'medico', '', 'pendiente'))
            self.assertEqual(list(migrated.groups.values_list('pk', flat=True)), [group.pk])
            other = Usuario.objects.get(pk=ambiguous.pk)
            self.assertEqual(other.authorized_role, '')
            self.assertEqual(other.requested_role, '')
            self.assertTrue(other.is_superuser)
            self.assertEqual(list(HistoriaClinica.objects.values()), clinical_before)
            self.assertEqual(HistoriaClinica.objects.get(pk=history.pk).estudiante_id, patient.pk)
            self.assertEqual(AccountAudit.objects.filter(action='legacy_review_pending').count(), 2)
            # A later administrative decision must survive reversal of the queue.
            from .services import review_account
            admin = Usuario.objects.get(email='initial@example.invalid')
            review_account(actor=admin, target_id=other.pk, action='approve', role='enfermera', reason='Revisión sintética posterior')
            MigrationExecutor(connection).migrate([('LoginRegister', '0003_account_approval_schema')])
            self.assertEqual(Usuario.objects.get(pk=old.pk).approval_status, 'legacy')
            self.assertEqual(Usuario.objects.get(pk=other.pk).authorized_role, 'enfermera')
            self.assertEqual(AccountAudit.objects.filter(action='legacy_review_rollback').count(), 1)
        finally:
            # Restore all leaves, preserving the verified administrator.
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
