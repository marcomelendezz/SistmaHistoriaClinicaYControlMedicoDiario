from unittest.mock import patch
from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from LoginRegister.test_security import account, login_as
from .models import Atencion, AuditoriaClinica, CambioEstadoAtencion, HistoriaClinica
from .services import correct_history, create_history, register_arrival, register_patient, transition_attention
from .test_patients import personal_data


CLINICAL = dict(fecha_consulta='2026-10-28', motivo_consulta='Consulta ficticia',
    diagnostico='Diagnóstico ficticio', tratamiento='Tratamiento ficticio', observaciones='Prueba sintética')


class AttentionWorkflowTests(TestCase):
    def setUp(self):
        self.nurse = account('nurse@example.invalid', 'enfermera')
        self.doctor = account('doctor@example.invalid', 'medico')
        self.admin = account('admin@example.invalid', 'administrador', is_superuser=True)
        self.patient = register_patient(actor=self.nurse, data=personal_data())
        login_as(self.client, self.nurse)

    def arrival(self):
        return register_arrival(actor=self.nurse, patient_id=self.patient.pk, arrival=timezone.now(), reason='Motivo ficticio')

    def started(self):
        attention = self.arrival()
        return transition_attention(actor=self.nurse, attention_id=attention.pk, target='en_atencion', expected_version=attention.version)

    def completed(self):
        attention = self.started()
        history = create_history(actor=self.doctor, patient_id=self.patient.pk, attention_id=attention.pk, data=CLINICAL)
        return attention, history

    def test_nurse_registers_arrival_without_creating_or_accepting_clinical_data(self):
        response = self.client.post(reverse('nueva_consulta'), {'estudiante': self.patient.pk,
            'arrival': timezone.localtime().strftime('%Y-%m-%dT%H:%M'), 'reason': 'Motivo ficticio', **CLINICAL})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(HistoriaClinica.objects.count(), 0)
        attention = Atencion.objects.get()
        self.assertEqual(attention.estado, 'pendiente')
        self.assertEqual(attention.registrada_por, self.nurse)
        self.assertEqual(CambioEstadoAtencion.objects.get().nuevo, 'pendiente')

    def test_nurse_can_start_but_cannot_finalize_attention_or_write_history(self):
        attention = self.started()
        self.assertEqual(attention.estado, 'en_atencion')
        self.assertEqual(attention.actualizada_por, self.nurse)
        with self.assertRaises(ValidationError):
            transition_attention(actor=self.nurse, attention_id=attention.pk, target='atendido', expected_version=attention.version)
        with self.assertRaises(PermissionDenied):
            create_history(actor=self.nurse, patient_id=self.patient.pk, attention_id=attention.pk, data=CLINICAL)
        self.assertEqual(self.client.get(reverse('consulta_medica', args=[attention.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse('consulta_medica', args=[attention.pk]), CLINICAL).status_code, 403)

    def test_only_complete_clinical_record_finishes_attention(self):
        attention = self.started()
        with self.assertRaises(ValidationError):
            create_history(actor=self.doctor, patient_id=self.patient.pk, attention_id=attention.pk, data={**CLINICAL, 'diagnostico': ''})
        attention.refresh_from_db()
        self.assertEqual(attention.estado, 'en_atencion')
        self.assertFalse(HistoriaClinica.objects.exists())
        history = create_history(actor=self.doctor, patient_id=self.patient.pk, attention_id=attention.pk, data=CLINICAL)
        attention.refresh_from_db()
        self.assertEqual(attention.estado, 'atendido')
        self.assertEqual(history.medico, self.doctor)
        self.assertEqual(history.atencion, attention)
        self.assertEqual(list(attention.cambios_estado.values_list('nuevo', flat=True)), ['pendiente', 'en_atencion', 'atendido'])

    def test_cancellation_keeps_attention_and_trace_and_allows_future_visit(self):
        attention = self.arrival()
        transition_attention(actor=self.nurse, attention_id=attention.pk, target='cancelado', expected_version=0)
        attention.refresh_from_db()
        self.assertEqual(attention.estado, 'cancelado')
        self.assertEqual(attention.cambios_estado.count(), 2)
        self.assertNotEqual(self.arrival().pk, attention.pk)
        self.assertFalse(HistoriaClinica.objects.exists())

    def test_open_visit_is_unique_in_service_and_database(self):
        self.arrival()
        with self.assertRaises(ValidationError):
            self.arrival()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Atencion.objects.create(paciente=self.patient, fecha_hora_llegada=timezone.now(), motivo_visita='Ficticio',
                registrada_por=self.nurse, actualizada_por=self.nurse)
        self.assertEqual(Atencion.objects.count(), 1)

    def test_outdated_state_change_and_invalid_transitions_are_rejected(self):
        attention = self.started()
        with self.assertRaises(ValidationError):
            transition_attention(actor=self.doctor, attention_id=attention.pk, target='cancelado', expected_version=0)
        with self.assertRaises(ValidationError):
            transition_attention(actor=self.doctor, attention_id=attention.pk, target='pendiente', expected_version=attention.version)

    def test_admin_cannot_register_arrive_start_or_write_clinical_information(self):
        attention = self.arrival()
        login_as(self.client, self.admin)
        self.assertEqual(self.client.get(reverse('nueva_consulta')).status_code, 403)
        self.assertEqual(self.client.post(reverse('cambiar_estado', args=[attention.pk]), {'target': 'en_atencion', 'expected_version': 0}).status_code, 403)
        self.assertEqual(self.client.get(reverse('consulta_medica', args=[attention.pk])).status_code, 403)
        with self.assertRaises(PermissionDenied):
            register_arrival(actor=self.admin, patient_id=self.patient.pk, arrival=timezone.now(), reason='Ficticio')
        with self.assertRaises(PermissionDenied):
            transition_attention(actor=self.admin, attention_id=attention.pk, target='en_atencion', expected_version=0)

    def test_correction_requires_reason_and_reconstructs_previous_values(self):
        _, history = self.completed()
        before = history.diagnostico
        with self.assertRaises(ValidationError):
            correct_history(actor=self.doctor, history_id=history.pk, data={'diagnostico': 'Corregido'}, reason='', expected_version=0)
        corrected = correct_history(actor=self.doctor, history_id=history.pk,
            data={'diagnostico': 'Corregido'}, reason='Motivo clínico ficticio', expected_version=0)
        event = corrected.cambios_clinicos.first()
        self.assertEqual(event.anteriores, {'diagnostico': before})
        self.assertEqual(event.nuevos, {'diagnostico': 'Corregido'})
        self.assertEqual(event.usuario, self.doctor)
        self.assertEqual(event.motivo, 'Motivo clínico ficticio')
        self.assertEqual(corrected.version, 1)
        with self.assertRaises(ValidationError):
            correct_history(actor=self.doctor, history_id=history.pk, data={'diagnostico': 'Otra edición'}, reason='Ficticio', expected_version=0)

    def test_nurse_and_administrator_cannot_correct_even_with_technical_superuser_flags(self):
        _, history = self.completed()
        for actor in [self.nurse, self.admin]:
            login_as(self.client, actor)
            self.assertEqual(self.client.get(reverse('corregir_historia', args=[history.pk])).status_code, 403)
            with self.assertRaises(PermissionDenied):
                correct_history(actor=actor, history_id=history.pk, data={'diagnostico': 'No autorizado'}, reason='Ficticio', expected_version=0)

    def test_clinical_audit_failure_rolls_back_completion(self):
        attention = self.started()
        with patch('Hisotria_clinica.services.AuditoriaClinica.objects.create', side_effect=RuntimeError('Synthetic')):
            with self.assertRaises(RuntimeError):
                create_history(actor=self.doctor, patient_id=self.patient.pk, attention_id=attention.pk, data=CLINICAL)
        attention.refresh_from_db()
        self.assertEqual(attention.estado, 'en_atencion')
        self.assertFalse(HistoriaClinica.objects.exists())

    def test_clinical_audit_failure_rolls_back_correction(self):
        _, history = self.completed()
        with patch('Hisotria_clinica.services.AuditoriaClinica.objects.create', side_effect=RuntimeError('Synthetic')):
            with self.assertRaises(RuntimeError):
                correct_history(actor=self.doctor, history_id=history.pk, data={'diagnostico': 'No guardar'}, reason='Ficticio', expected_version=0)
        history.refresh_from_db()
        self.assertEqual(history.diagnostico, CLINICAL['diagnostico'])
        self.assertEqual(history.version, 0)

    def test_patient_mismatch_pending_or_already_completed_visit_cannot_create_history(self):
        attention = self.arrival()
        with self.assertRaises(ValidationError):
            create_history(actor=self.doctor, patient_id=self.patient.pk, attention_id=attention.pk, data=CLINICAL)
        attention = transition_attention(actor=self.nurse, attention_id=attention.pk, target='en_atencion', expected_version=0)
        other = register_patient(actor=self.nurse, data=personal_data(cedula='E-999'))
        with self.assertRaises(ValidationError):
            create_history(actor=self.doctor, patient_id=other.pk, attention_id=attention.pk, data=CLINICAL)
        create_history(actor=self.doctor, patient_id=self.patient.pk, attention_id=attention.pk, data=CLINICAL)
        with self.assertRaises(ValidationError):
            create_history(actor=self.doctor, patient_id=self.patient.pk, attention_id=attention.pk, data=CLINICAL)

    def test_browser_forms_finish_and_correct_with_audited_reason(self):
        attention = self.started()
        login_as(self.client, self.doctor)
        self.assertContains(self.client.get(reverse('consulta_medica', args=[attention.pk])), 'value="' + timezone.localdate().isoformat() + '"')
        response = self.client.post(reverse('consulta_medica', args=[attention.pk]), CLINICAL)
        self.assertEqual(response.status_code, 302)
        history = HistoriaClinica.objects.get()
        payload = {**CLINICAL, 'diagnostico': 'Cambio ficticio', 'expected_version': history.version}
        result = self.client.post(reverse('corregir_historia', args=[history.pk]), payload)
        self.assertEqual(result.status_code, 200)
        self.assertIn('reason', result.context['form'].errors)
        payload['reason'] = 'Justificación clínica ficticia'
        self.assertEqual(self.client.post(reverse('corregir_historia', args=[history.pk]), payload).status_code, 302)
        self.assertEqual(history.cambios_clinicos.count(), 2)

    def test_filters_and_read_only_admin_visibility(self):
        attention = self.arrival()
        login_as(self.client, self.admin)
        response = self.client.get(reverse('lista_atenciones'), {'estado': 'pendiente', 'q': self.patient.cedula})
        self.assertEqual(list(response.context['attentions']), [attention])
        self.assertNotContains(response, 'name="target"')
        self.assertEqual(self.client.get(reverse('lista_atenciones'), {'fecha': 'not-a-date'}).context['attentions'].count(), 0)

    def test_state_and_medical_endpoints_require_csrf(self):
        attention = self.started()
        client = Client(enforce_csrf_checks=True)
        login_as(client, self.doctor)
        self.assertEqual(client.post(reverse('consulta_medica', args=[attention.pk]), CLINICAL).status_code, 403)
        self.assertEqual(client.post(reverse('cambiar_estado', args=[attention.pk]), {'target': 'cancelado', 'expected_version': 1}).status_code, 403)

    def test_completed_visit_cannot_be_cancelled_or_overwritten_and_patient_cannot_be_deleted(self):
        from django.db.models.deletion import ProtectedError
        attention, history = self.completed()
        attention.refresh_from_db()
        with self.assertRaises(ValidationError):
            transition_attention(actor=self.nurse, attention_id=attention.pk, target='cancelado', expected_version=attention.version)
        with self.assertRaises(ProtectedError):
            self.patient.delete()
        self.assertEqual(HistoriaClinica.objects.get(pk=history.pk).diagnostico, CLINICAL['diagnostico'])

    def test_dashboard_counts_completed_consultations_separately_from_cancelled_arrivals(self):
        attention = self.arrival()
        self.assertEqual(self.client.get(reverse('dashboard')).context['pending'], 1)
        transition_attention(actor=self.nurse, attention_id=attention.pk, target='cancelado', expected_version=0)
        self.completed()
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.context['completed_today'], 1)
        self.assertEqual(response.context['pending'], 0)

    def test_historical_correction_does_not_invent_original_doctor_or_arrival(self):
        history = HistoriaClinica.objects.create(estudiante=self.patient, **CLINICAL)
        corrected = correct_history(actor=self.doctor, history_id=history.pk, data={'diagnostico': 'Corrección ficticia'}, reason='Justificación ficticia', expected_version=0)
        self.assertIsNone(corrected.medico_id)
        self.assertIsNone(corrected.atencion_id)
        self.assertEqual(corrected.cambios_clinicos.get().usuario, self.doctor)

    def test_dashboard_uses_completion_day_instead_of_arrival_day(self):
        attention = register_arrival(actor=self.nurse, patient_id=self.patient.pk,
            arrival=timezone.now()-timedelta(days=1), reason='Visita ficticia anterior')
        transition_attention(actor=self.nurse, attention_id=attention.pk, target='en_atencion', expected_version=0)
        create_history(actor=self.doctor, patient_id=self.patient.pk, attention_id=attention.pk, data=CLINICAL)
        self.assertEqual(self.client.get(reverse('dashboard')).context['completed_today'], 1)
