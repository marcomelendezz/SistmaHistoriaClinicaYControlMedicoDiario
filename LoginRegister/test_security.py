from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command, CommandError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .access import has_capability
from .models import AccountAudit
from .services import accounts_for, account_audit_for, review_account


PASSWORD = 'Synthetic-Password-Only-2026!'
User = get_user_model()


def account(email, role='', status='aprobado', **extra):
    return User.objects.create_user(email=email, password=PASSWORD, nombre='Persona',
        apellido='Ficticia', authorized_role=role, approval_status=status, **extra)


def login_as(client, user):
    client.force_login(user, backend='django.contrib.auth.backends.ModelBackend')


class RegistrationAndAuthenticationTests(TestCase):
    def registration(self, **changes):
        data = {'nombre': 'Solicitud', 'apellido': 'Ficticia', 'email': 'request@example.invalid',
            'requested_role': 'medico', 'password1': PASSWORD, 'password2': PASSWORD}
        data.update(changes)
        return self.client.post(reverse('register'), data)

    def test_registration_is_pending_and_ignores_privilege_injection(self):
        response = self.registration(authorized_role='administrador', approval_status='aprobado', is_staff='on', is_superuser='on')
        self.assertRedirects(response, reverse('login'))
        user = User.objects.get()
        self.assertEqual(user.requested_role, 'medico')
        self.assertEqual(user.approval_status, 'pendiente')
        self.assertEqual(user.authorized_role, '')
        self.assertFalse(user.is_staff or user.is_superuser)
        self.assertFalse(user.groups.exists())
        self.assertTrue(user.check_password(PASSWORD))

    def test_registration_only_allows_medical_or_nursing_requests(self):
        for role in ['administrador', 'superuser', '']:
            with self.subTest(role=role):
                self.assertEqual(self.registration(requested_role=role).status_code, 200)
                self.assertFalse(User.objects.exists())
        self.registration(requested_role='enfermera')
        self.assertEqual(User.objects.get().requested_role, 'enfermera')

    def test_duplicate_email_is_rejected_case_insensitively(self):
        account('REQUEST@example.invalid')
        self.assertEqual(self.registration().status_code, 200)
        self.assertEqual(User.objects.count(), 1)

    def test_pending_rejected_legacy_and_unassigned_accounts_cannot_login(self):
        for index, (status, role) in enumerate([('pendiente', ''), ('rechazado', 'medico'), ('legacy', ''), ('aprobado', '')]):
            user = account(f'blocked{index}@example.invalid', role, status)
            response = self.client.post(reverse('login'), {'username': user.email, 'password': PASSWORD})
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'Tu cuenta está pendiente de aprobación')
            self.assertNotIn('_auth_user_id', self.client.session)

    def test_approved_user_can_login_and_logout_requires_post(self):
        user = account('doctor@example.invalid', 'medico')
        response = self.client.post(reverse('login'), {'username': user.email, 'password': PASSWORD})
        self.assertRedirects(response, reverse('dashboard'))
        self.assertEqual(self.client.get(reverse('logout')).status_code, 405)
        self.assertIn('_auth_user_id', self.client.session)
        self.assertContains(self.client.get(reverse('dashboard')), 'action="/logout/"')
        self.assertRedirects(self.client.post(reverse('logout')), reverse('login'))
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_axes_still_locks_out_failed_logins(self):
        user = account('axes@example.invalid', 'medico')
        responses = [self.client.post(reverse('login'), {'username': user.email, 'password': 'wrong'}) for _ in range(3)]
        self.assertEqual(responses[-1].status_code, 302)
        self.assertIn('/bloqueo/', responses[-1].url)
        response = self.client.post(reverse('login'), {'username': user.email, 'password': PASSWORD})
        self.assertEqual(response.status_code, 302)
        self.assertIn('/bloqueo/', response.url)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_login_and_logout_have_csrf_protection(self):
        client = Client(enforce_csrf_checks=True)
        user = account('csrf@example.invalid', 'medico')
        self.assertEqual(client.post(reverse('login'), {'username': user.email, 'password': PASSWORD}).status_code, 403)
        login_as(client, user)
        self.assertEqual(client.post(reverse('logout')).status_code, 403)

    def test_lockout_of_one_account_does_not_block_another_on_shared_network(self):
        blocked = account('blocked@example.invalid', 'medico')
        administrator = account('administrator@example.invalid', 'administrador')
        for _ in range(3):
            self.client.post(reverse('login'), {'username': blocked.email, 'password': 'wrong'})
        response = self.client.post(reverse('login'), {'username': administrator.email, 'password': PASSWORD})
        self.assertRedirects(response, reverse('dashboard'))

    def test_old_superuser_flags_do_not_grant_institutional_access(self):
        user = User.objects.create_superuser(email='legacy-super@example.invalid', password=PASSWORD)
        self.assertEqual(user.approval_status, 'pendiente')
        self.assertEqual(user.authorized_role, '')
        self.assertFalse(has_capability(user, 'write_clinical'))
        self.assertFalse(has_capability(user, 'manage_accounts'))
        login_as(self.client, user)
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 403)
        self.assertEqual(self.client.get('/admin/').status_code, 302)

    def test_reset_does_not_approve_account_and_token_cannot_be_reused(self):
        user = account('pending@example.invalid', '', 'pendiente')
        self.client.post(reverse('password_reset'), {'email': user.email})
        self.assertEqual(len(mail.outbox), 1)
        token = default_token_generator.make_token(user)
        url = reverse('password_reset_confirm', kwargs={'uidb64': urlsafe_base64_encode(force_bytes(user.pk)), 'token': token})
        response = self.client.get(url)
        new_password = 'Another-Synthetic-Password-2026!'
        self.assertRedirects(self.client.post(response.url, {'new_password1': new_password, 'new_password2': new_password}), reverse('password_reset_complete'))
        user.refresh_from_db()
        self.assertTrue(user.check_password(new_password))
        self.assertEqual(user.approval_status, 'pendiente')
        self.assertEqual(user.authorized_role, '')
        self.assertFalse(default_token_generator.check_token(user, token))

    def test_reset_for_unknown_email_has_same_public_response(self):
        self.assertRedirects(self.client.post(reverse('password_reset'), {'email': 'absent@example.invalid'}), reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 0)

    def test_password_reset_rejects_short_password_and_invalid_token(self):
        user = account('reset@example.invalid', 'medico')
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        invalid = self.client.get(reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': 'invalid-token'}))
        self.assertFalse(invalid.context['validlink'])
        valid = self.client.get(reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': token}))
        result = self.client.post(valid.url, {'new_password1': 'Short!123', 'new_password2': 'Short!123'})
        self.assertIn('new_password2', result.context['form'].errors)
        user.refresh_from_db()
        self.assertTrue(user.check_password(PASSWORD))


class AdministrativeApprovalTests(TestCase):
    def setUp(self):
        self.admin = account('admin@example.invalid', 'administrador')
        self.pending = account('pending@example.invalid', '', 'pendiente')
        self.pending.requested_role = 'medico'
        self.pending.save()
        login_as(self.client, self.admin)

    def decision(self, **changes):
        data = {'action': 'approve', 'role': 'enfermera', 'reason': 'Verificación institucional ficticia'}
        data.update(changes)
        return self.client.post(reverse('account_review', args=[self.pending.pk]), data)

    def test_admin_assigns_different_role_and_records_audit(self):
        self.assertRedirects(self.decision(), reverse('account_list'))
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.requested_role, 'medico')
        self.assertEqual(self.pending.authorized_role, 'enfermera')
        self.assertEqual(self.pending.approval_status, 'aprobado')
        self.assertEqual(self.pending.reviewed_by, self.admin)
        event = AccountAudit.objects.get()
        self.assertEqual(event.before['authorized_role'], '')
        self.assertEqual(event.after['authorized_role'], 'enfermera')
        self.assertNotIn('password', event.after)
        self.assertFalse(self.pending.is_superuser)

    def test_admin_can_reject_deactivate_and_reactivate_approved_account(self):
        self.decision(action='reject')
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.approval_status, 'rechazado')
        self.decision()
        self.decision(action='deactivate')
        self.pending.refresh_from_db()
        self.assertFalse(self.pending.is_active)
        self.decision(action='activate')
        self.pending.refresh_from_db()
        self.assertTrue(self.pending.is_active)
        self.assertEqual(AccountAudit.objects.count(), 4)

    def test_invalid_decisions_do_not_change_account(self):
        for changes in [{'role': ''}, {'role': 'superuser'}, {'action': 'activate'}]:
            with self.subTest(changes=changes):
                self.assertEqual(self.decision(**changes).status_code, 200)
                self.pending.refresh_from_db()
                self.assertEqual(self.pending.approval_status, 'pendiente')
                self.assertEqual(AccountAudit.objects.count(), 0)

    def test_nurse_and_doctor_cannot_administer_or_read_account_audit(self):
        for role in ['medico', 'enfermera']:
            user = account(role+'@example.invalid', role, is_staff=True, is_superuser=True)
            login_as(self.client, user)
            self.assertEqual(self.client.get(reverse('account_list')).status_code, 403)
            self.assertEqual(self.decision().status_code, 403)
            self.assertEqual(self.client.get(reverse('account_audit')).status_code, 403)
            self.assertEqual(self.client.get('/admin/').status_code, 302)
            for service in [accounts_for, account_audit_for]:
                with self.assertRaises(PermissionDenied):
                    service(user)

    def test_approval_assignment_and_rejection_need_no_reason_but_keep_audit(self):
        response = self.client.post(reverse('account_review', args=[self.pending.pk]), {'action': 'approve', 'role': 'medico'})
        self.assertRedirects(response, reverse('account_list'))
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.authorized_role, 'medico')
        self.assertEqual(self.pending.reviewed_by, self.admin)
        self.assertIsNotNone(self.pending.reviewed_at)
        event = AccountAudit.objects.get()
        self.assertEqual(event.reason, '')
        self.assertEqual(event.after['authorized_role'], 'medico')
        self.assertEqual(event.actor, self.admin)
        self.assertNotContains(self.client.get(reverse('account_list')), '<th>Activa</th>', html=True)
        response = self.client.post(reverse('account_review', args=[self.pending.pk]), {'action': 'reject'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(AccountAudit.objects.count(), 2)

    def test_administrator_cannot_change_own_role_or_disable_itself(self):
        for action in ['reject', 'deactivate', 'approve']:
            with self.assertRaises(PermissionDenied):
                review_account(actor=self.admin, target_id=self.admin.pk, action=action, role='medico', reason='Prueba')
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)
        self.assertEqual(self.admin.authorized_role, 'administrador')

    def test_audit_failure_rolls_back_approval(self):
        with patch('LoginRegister.services.AccountAudit.objects.create', side_effect=RuntimeError('synthetic failure')):
            with self.assertRaises(RuntimeError):
                review_account(actor=self.admin, target_id=self.pending.pk, action='approve', role='medico', reason='Prueba')
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.approval_status, 'pendiente')

    def test_session_and_stale_objects_lose_permissions_immediately(self):
        user = account('doctor@example.invalid', 'medico')
        client = Client()
        login_as(client, user)
        self.assertEqual(client.get(reverse('dashboard')).status_code, 200)
        review_account(actor=self.admin, target_id=user.pk, action='reject', reason='Revisión de autorización')
        self.assertFalse(has_capability(user, 'write_clinical'))
        self.assertEqual(client.get(reverse('dashboard')).status_code, 403)
        review_account(actor=self.admin, target_id=user.pk, action='deactivate', reason='Desactivación')
        self.assertEqual(client.get(reverse('dashboard')).status_code, 302)

    def test_csrf_required_for_administrative_decisions(self):
        client = Client(enforce_csrf_checks=True)
        login_as(client, self.admin)
        self.assertEqual(client.post(reverse('account_review', args=[self.pending.pk]), {'action': 'approve', 'role': 'medico', 'reason': 'Prueba'}).status_code, 403)

    def test_audit_is_read_only_and_renders_changes(self):
        self.decision()
        self.assertContains(self.client.get(reverse('account_audit')), 'Verificación institucional ficticia')
        before = list(AccountAudit.objects.values())
        self.client.post(reverse('account_audit'), {'action': 'delete'})
        self.assertEqual(list(AccountAudit.objects.values()), before)

    def test_profile_form_cannot_escalate_privileges(self):
        user = account('nurse@example.invalid', 'enfermera')
        login_as(self.client, user)
        self.client.post(reverse('editar_perfil'), {'nombre': 'Persona', 'apellido': 'Ficticia', 'email': user.email,
            'authorized_role': 'administrador', 'approval_status': 'aprobado', 'is_superuser': True})
        user.refresh_from_db()
        self.assertEqual(user.authorized_role, 'enfermera')
        self.assertFalse(user.is_superuser)


class BootstrapAdministratorTests(TestCase):
    def command(self, **options):
        call_command('bootstrap_admin', stdout=StringIO(), **options)

    def test_new_administrator_is_verified_and_can_login(self):
        with patch('LoginRegister.management.commands.bootstrap_admin.getpass', side_effect=[PASSWORD, PASSWORD]):
            self.command(email='initial@example.invalid', nombre='Administrador', apellido='Ficticio')
        user = User.objects.get()
        self.assertEqual(user.authorized_role, 'administrador')
        self.assertEqual(user.approval_status, 'aprobado')
        self.assertFalse(user.is_superuser)
        self.assertFalse(has_capability(user, 'write_clinical'))
        self.assertEqual(AccountAudit.objects.get().action, 'bootstrap_verified')
        self.client.post(reverse('login'), {'username': user.email, 'password': PASSWORD})
        self.assertEqual(self.client.get(reverse('account_list')).status_code, 200)

    def test_designation_preserves_password_identifier_and_legacy_role(self):
        user = account('old@example.invalid', '', 'legacy', cargo='Ambiguo', is_superuser=True)
        previous = (user.pk, user.password, user.cargo, user.is_superuser)
        with patch('LoginRegister.management.commands.bootstrap_admin.getpass', return_value=PASSWORD):
            self.command(email=user.email, designate_existing=True)
        user.refresh_from_db()
        self.assertEqual((user.pk, user.password, user.cargo, user.is_superuser), previous)
        self.assertFalse(has_capability(user, 'write_clinical'))

    @override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.PBKDF2PasswordHasher'])
    def test_designation_and_verification_preserve_older_password_hash(self):
        from django.contrib.auth.hashers import PBKDF2PasswordHasher
        user = account('older-hash@example.invalid', '', 'legacy')
        previous = PBKDF2PasswordHasher().encode(PASSWORD, 'syntheticSalt', iterations=12000)
        user.password = previous
        user.save(update_fields=['password'])
        for mode in [{'designate_existing': True}, {'verify': True}]:
            with patch('LoginRegister.management.commands.bootstrap_admin.getpass', return_value=PASSWORD):
                self.command(email=user.email, **mode)
            user.refresh_from_db()
            self.assertEqual(user.password, previous)

    def test_existing_account_requires_explicit_designation(self):
        user = account('old@example.invalid', '', 'legacy')
        with self.assertRaises(CommandError):
            self.command(email=user.email)
        user.refresh_from_db()
        self.assertEqual(user.approval_status, 'legacy')

    def test_wrong_password_cannot_designate_existing_user(self):
        user = account('old@example.invalid', '', 'legacy')
        with patch('LoginRegister.management.commands.bootstrap_admin.getpass', return_value='incorrect'):
            with self.assertRaises(CommandError):
                self.command(email=user.email, designate_existing=True)
        user.refresh_from_db()
        self.assertEqual(user.authorized_role, '')
        self.assertFalse(AccountAudit.objects.exists())

    def test_weak_or_mismatched_password_creates_no_account(self):
        for passwords in [('short', 'short'), (PASSWORD, 'mismatch')]:
            with patch('LoginRegister.management.commands.bootstrap_admin.getpass', side_effect=passwords):
                with self.assertRaises(CommandError):
                    self.command(email='initial@example.invalid', nombre='Administrador', apellido='Ficticio')
            self.assertFalse(User.objects.exists())

    def test_verification_requires_active_approved_administrator(self):
        user = account('nurse@example.invalid', 'enfermera')
        with self.assertRaises(CommandError):
            self.command(email=user.email, verify=True)

    def test_verified_administrator_can_be_verified_again_without_changing_password(self):
        user = account('admin@example.invalid', 'administrador')
        previous = user.password
        with patch('LoginRegister.management.commands.bootstrap_admin.getpass', return_value=PASSWORD):
            self.command(email=user.email, verify=True)
        user.refresh_from_db()
        self.assertEqual(user.password, previous)
        self.assertEqual(AccountAudit.objects.get().action, 'bootstrap_verified')

    def test_bootstrap_does_not_require_axes_schema_during_initial_stage(self):
        with patch('LoginRegister.management.commands.bootstrap_admin.connection.introspection.table_names', return_value=[User._meta.db_table, AccountAudit._meta.db_table]):
            with patch('LoginRegister.management.commands.bootstrap_admin.getpass', side_effect=[PASSWORD, PASSWORD]):
                self.command(email='fresh@example.invalid', nombre='Administrador', apellido='Ficticio')
        self.assertTrue(has_capability(User.objects.get(), 'manage_accounts'))

    def test_missing_schema_produces_actionable_error(self):
        with patch('LoginRegister.management.commands.bootstrap_admin.connection.introspection.table_names', return_value=[]):
            with self.assertRaisesRegex(CommandError, '0003'):
                self.command(email='fresh@example.invalid', nombre='Administrador', apellido='Ficticio')
