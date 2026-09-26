from django.test import TestCase
from django.urls import reverse

from .models import Estudiante, HistoriaClinica


class HistoriaClinicaViewTests(TestCase):
    def test_creates_student_and_history_from_forms(self):
        payload = {
            'nombre': 'Ana',
            'apellido': 'Gómez',
            'cedula': '12345678',
            'edad': 28,
            'edo_civil': 'Soltera',
            'sexo': 'Femenino',
            'direccion': 'Calle 1',
            'contacto_emergencia': 'Pedro Gómez',
            'telefono': '04145556677',
            'fecha_nacimiento': '1998-04-15',
            'fecha_consulta': '2026-09-26',
            'motivo_consulta': 'Dolor de cabeza',
            'diagnostico': 'Migraña',
            'tratamiento': 'Tomar acetaminofén',
            'observaciones': 'Sin novedad',
        }

        response = self.client.post(reverse('registro_historia'), payload)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Estudiante.objects.count(), 1)
        self.assertEqual(HistoriaClinica.objects.count(), 1)
        self.assertEqual(HistoriaClinica.objects.first().estudiante.nombre, 'Ana')
