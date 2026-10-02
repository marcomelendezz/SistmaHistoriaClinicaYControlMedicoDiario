from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse


class MiPerfilViewTests(TestCase):
	def setUp(self):
		self.usuario = get_user_model().objects.create_user(
			email='medico@example.com',
			password='test-password-123',
			nombre='Ana',
			apellido='Perez',
			cargo='Medico',
		)

	def test_muestra_datos_del_usuario_autenticado(self):
		self.client.force_login(self.usuario)

		response = self.client.get(reverse('mi_perfil'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Ana')
		self.assertContains(response, 'Perez')
		self.assertContains(response, 'medico@example.com')
		self.assertContains(response, 'Medico')

	def test_redirige_al_login_si_no_hay_sesion(self):
		response = self.client.get(reverse('mi_perfil'))

		self.assertEqual(response.status_code, 302)
		self.assertTrue(response.url.startswith(f"{reverse('login')}?next="))

	def test_edita_datos_del_usuario_autenticado(self):
		self.client.force_login(self.usuario)

		response = self.client.post(reverse('editar_perfil'), {
			'nombre': 'Ana Maria',
			'apellido': 'Lopez',
			'email': 'ana@example.com',
			'cargo': 'Enfermero/a',
		})

		self.usuario.refresh_from_db()
		self.assertRedirects(response, reverse('mi_perfil'))
		self.assertEqual(self.usuario.nombre, 'Ana Maria')
		self.assertEqual(self.usuario.apellido, 'Lopez')
		self.assertEqual(self.usuario.email, 'ana@example.com')
		self.assertEqual(self.usuario.cargo, 'Medico')
