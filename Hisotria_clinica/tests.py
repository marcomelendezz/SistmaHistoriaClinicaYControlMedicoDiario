from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from LoginRegister.test_security import account, login_as
from .models import Atencion, Estudiante, HistoriaClinica
from .test_patients import personal_data
from .test_workflow import CLINICAL


class HistoriaClinicaViewTests(TestCase):
    def test_patient_arrival_and_medical_consultation_are_separate(self):
        doctor = account('doctor@example.invalid', 'medico')
        login_as(self.client, doctor)
        self.assertEqual(self.client.post(reverse('registro_historia'), {**personal_data(), **CLINICAL}).status_code, 405)
        self.assertEqual(Estudiante.objects.count(), 0)
        self.assertEqual(self.client.post(reverse('registro_paciente'), personal_data()).status_code, 302)
        patient = Estudiante.objects.get()
        self.assertEqual(HistoriaClinica.objects.count(), 0)
        self.assertEqual(Atencion.objects.count(), 0)
        self.assertEqual(self.client.post(reverse('nueva_consulta'), {'estudiante': patient.pk,
            'arrival': timezone.localtime().strftime('%Y-%m-%dT%H:%M'), 'reason': 'Motivo ficticio'}).status_code, 302)
        attention = Atencion.objects.get()
        self.assertEqual(HistoriaClinica.objects.count(), 0)
        self.client.post(reverse('cambiar_estado', args=[attention.pk]), {'target': 'en_atencion', 'expected_version': 0})
        self.assertEqual(self.client.post(reverse('consulta_medica', args=[attention.pk]), CLINICAL).status_code, 302)
        self.assertEqual(HistoriaClinica.objects.get().estudiante_id, patient.pk)
        attention.refresh_from_db()
        self.assertEqual(attention.estado, 'atendido')
