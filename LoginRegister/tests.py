from django.test import TestCase
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
