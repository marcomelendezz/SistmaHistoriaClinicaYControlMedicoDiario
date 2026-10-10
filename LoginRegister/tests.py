from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from .forms import RegistroForm


class RegistroFormPasswordTests(TestCase):
	def build_form(self, password, confirmation=None):
		return RegistroForm(data={
			'nombre': 'Ana',
			'apellido': 'Perez',
			'email': 'ana@example.com',
			'cargo': 'Medico',
			'password1': password,
			'password2': password if confirmation is None else confirmation,
		})

	def test_rejects_password_shorter_than_16_characters(self):
		form = self.build_form('ClaveSegura!202')

		self.assertFalse(form.is_valid())
		self.assertIn(
			'La contraseña es muy corta; debe tener al menos 16 caracteres.',
			form.errors['password1'],
		)

	def test_reports_password_mismatch_even_when_password_is_too_short(self):
		form = self.build_form('Clave1234', 'Clave12345')

		self.assertFalse(form.is_valid())
		self.assertIn('Las contraseñas no coinciden.', form.errors['password2'])

	def test_accepts_password_with_16_characters(self):
		form = self.build_form('ClaveSegura!2026')

		self.assertEqual(len('ClaveSegura!2026'), 16)
		self.assertTrue(form.is_valid(), form.errors)


class PasswordResetFlowTests(TestCase):
	@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
	def test_password_can_be_reset_from_email_link(self):
		user = get_user_model().objects.create_user(
			email='ana@example.com',
			password='Old-Password!123456',
			nombre='Ana',
			apellido='Perez',
			cargo='Medico',
		)

		response = self.client.post(
			reverse('password_reset'),
			{'email': user.email},
		)
		self.assertRedirects(response, reverse('password_reset_done'))
		self.assertEqual(len(mail.outbox), 1)
		self.assertIn('password-reset/', mail.outbox[0].body)

		uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
		token = default_token_generator.make_token(user)
		confirm_url = reverse(
			'password_reset_confirm',
			kwargs={'uidb64': uidb64, 'token': token},
		)
		response = self.client.get(confirm_url)
		self.assertRedirects(
			response,
			reverse(
				'password_reset_confirm',
				kwargs={'uidb64': uidb64, 'token': 'set-password'},
			),
		)
		response = self.client.post(
			response.url,
			{
				'new_password1': 'New-Strong-Passphrase-2026!',
				'new_password2': 'New-Strong-Passphrase-2026!',
			},
		)

		self.assertRedirects(response, reverse('password_reset_complete'))
		user.refresh_from_db()
		self.assertTrue(user.check_password('New-Strong-Passphrase-2026!'))

	def test_password_reset_and_lockout_pages_render(self):
		for url_name in (
			'password_reset',
			'password_reset_done',
			'password_reset_complete',
			'blocked',
		):
			with self.subTest(url_name=url_name):
				response = self.client.get(reverse(url_name))
				self.assertEqual(response.status_code, 200)
