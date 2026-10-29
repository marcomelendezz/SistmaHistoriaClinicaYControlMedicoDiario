from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from LoginRegister.test_security import account, login_as
from .models import Estudiante, HistoriaClinica
from .services import create_history, histories_for, patients_for, register_patient, register_patient_and_history, register_arrival, transition_attention


PATIENT = dict(nombre='Paciente', apellido='Ficticio', cedula='SYNTHETIC-001', edad=26, tipo_paciente='estudiante',
    edo_civil='Soltero', sexo='Masculino', direccion='Dirección ficticia',
    contacto_emergencia='Contacto ficticio', telefono='0000000000', fecha_nacimiento='2000-01-01')
HISTORY = dict(fecha_consulta='2026-10-27', motivo_consulta='Consulta sintética',
    diagnostico='Diagnóstico ficticio', tratamiento='Tratamiento ficticio', observaciones='Solo prueba')


class ClinicalAuthorizationTests(TestCase):
    def setUp(self):
        self.doctor = account('doctor@example.invalid', 'medico')
        self.nurse = account('nurse@example.invalid', 'enfermera')
        self.admin = account('admin@example.invalid', 'administrador', is_staff=True, is_superuser=True)
        self.patient = Estudiante.objects.create(**PATIENT)
        self.history = HistoriaClinica.objects.create(estudiante=self.patient, **HISTORY)

    def test_nurse_and_admin_cannot_create_clinical_data_via_direct_post(self):
        attention = register_arrival(actor=self.nurse, patient_id=self.patient.pk, arrival=timezone.now(), reason='Ficticio')
        for user in [self.nurse, self.admin]:
            login_as(self.client, user)
            url = reverse('consulta_medica', args=[attention.pk])
            self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.post(url, HISTORY).status_code, 403)
        self.assertEqual(HistoriaClinica.objects.count(), 1)
        self.assertEqual(Estudiante.objects.count(), 1)

    def test_all_approved_roles_can_read_but_detail_accepts_no_writes(self):
        for user in [self.doctor, self.nurse, self.admin]:
            login_as(self.client, user)
            self.assertContains(self.client.get(reverse('detalle_historia', args=[self.history.pk])), HISTORY['diagnostico'])
            self.assertContains(self.client.get(reverse('lista_historia'), {'estudiante': self.patient.pk}, follow=True), self.patient.cedula)
            self.assertEqual(self.client.post(reverse('detalle_historia', args=[self.history.pk]), {'diagnostico': 'Cambio'}).status_code, 405)
        self.history.refresh_from_db()
        self.assertEqual(self.history.diagnostico, HISTORY['diagnostico'])

    def test_nurse_can_register_personal_details_without_creating_history(self):
        login_as(self.client, self.nurse)
        payload = {**PATIENT, 'cedula': 'SYNTHETIC-002', 'diagnostico': 'Intento de inyección'}
        self.assertEqual(self.client.post(reverse('registro_paciente'), payload).status_code, 302)
        self.assertEqual(Estudiante.objects.count(), 2)
        self.assertEqual(HistoriaClinica.objects.count(), 1)
        login_as(self.client, self.admin)
        self.assertEqual(self.client.post(reverse('registro_paciente'), payload).status_code, 403)

    def test_pending_rejected_and_legacy_accounts_cannot_read_identified_objects(self):
        for status in ['pendiente', 'rechazado', 'legacy']:
            user = account(status+'@example.invalid', 'medico', status)
            login_as(self.client, user)
            for url in [reverse('detalle_historia', args=[self.history.pk]), reverse('lista_historia')+'?estudiante='+str(self.patient.pk)]:
                self.assertEqual(self.client.get(url).status_code, 403)
            for query in [patients_for, histories_for]:
                with self.assertRaises(PermissionDenied):
                    query(user)

    def test_anonymous_access_redirects_before_lookup(self):
        for url in [reverse('detalle_historia', args=[self.history.pk]), reverse('lista_historia'), reverse('registro_historia')]:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.url.startswith('/?next='))

    def test_doctor_adds_consultations_without_overwriting_previous_history(self):
        login_as(self.client, self.doctor)
        attention = register_arrival(actor=self.nurse, patient_id=self.patient.pk, arrival=timezone.now(), reason='Ficticio')
        transition_attention(actor=self.nurse, attention_id=attention.pk, target='en_atencion', expected_version=0)
        self.assertEqual(self.client.post(reverse('consulta_medica', args=[attention.pk]), HISTORY).status_code, 302)
        self.assertEqual(HistoriaClinica.objects.filter(estudiante=self.patient).count(), 2)
        self.history.refresh_from_db()
        self.assertEqual(self.history.diagnostico, HISTORY['diagnostico'])

    def test_services_reject_nurse_and_admin_even_without_view(self):
        for user in [self.nurse, self.admin]:
            with self.assertRaises(PermissionDenied):
                create_history(actor=user, patient_id=self.patient.pk, data=HISTORY)
            with self.assertRaises(PermissionDenied):
                register_patient_and_history(actor=user, patient_data=PATIENT, history_data=HISTORY)
        with self.assertRaises(ValidationError):
            register_patient(actor=self.nurse, data={**PATIENT, 'diagnostico': 'No permitido'})

    def test_transaction_rolls_back_patient_if_history_validation_fails(self):
        with self.assertRaises(ValidationError):
            register_patient_and_history(actor=self.doctor, patient_data={**PATIENT, 'cedula': 'SYNTHETIC-002'}, history_data={**HISTORY, 'diagnostico': ''})
        self.assertEqual(Estudiante.objects.count(), 1)

    def test_navigation_matches_role(self):
        login_as(self.client, self.nurse)
        page = self.client.get(reverse('dashboard'))
        self.assertContains(page, reverse('registro_paciente'))
        self.assertContains(page, reverse('nueva_consulta'))
        self.assertNotContains(page, reverse('registro_historia'))
        self.assertNotContains(page, reverse('account_list'))
        login_as(self.client, self.admin)
        page = self.client.get(reverse('dashboard'))
        self.assertContains(page, reverse('account_list'))
        self.assertNotContains(page, reverse('registro_historia'))

    def test_nonexistent_history_has_no_data_leak(self):
        login_as(self.client, self.nurse)
        self.assertEqual(self.client.get(reverse('detalle_historia', args=[999999])).status_code, 404)

    def test_clinical_responses_cannot_be_cached(self):
        login_as(self.client, self.nurse)
        response = self.client.get(reverse('detalle_historia', args=[self.history.pk]))
        self.assertIn('no-store', response.headers['Cache-Control'])
        self.assertIn('private', response.headers['Cache-Control'])
