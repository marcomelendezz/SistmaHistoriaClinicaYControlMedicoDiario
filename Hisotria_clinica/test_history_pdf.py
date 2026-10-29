from datetime import date, timedelta
from io import BytesIO
from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfReader

from LoginRegister.test_security import account, login_as
from .forms import EstudianteForm
from .models import Atencion, AuditoriaClinica, AuditoriaPaciente, Estudiante, HistoriaClinica
from .pdf_histories import clinical_history_pdf
from .reports import REPORT_ZONE
from .services import correct_history, create_history, register_arrival, register_patient, transition_attention, update_patient
from .test_patients import personal_data


CLINICAL = dict(fecha_consulta=date(2026, 1, 15), motivo_consulta='MOTIVO FICTICIO ÚNICO',
                enfermedad_actual='ENFERMEDAD FICTICIA ÚNICA', diagnostico_provisional='PROVISIONAL FICTICIO ÚNICO',
                diagnostico='DIAGNÓSTICO INTERNO EXCLUIDO', tratamiento='TRATAMIENTO INTERNO EXCLUIDO',
                observaciones='OBSERVACIÓN INTERNA EXCLUIDA', rp=True, lab=True)


class HistoryPdfTests(TestCase):
    def setUp(self):
        self.nurse = account('hc-nurse@example.invalid', 'enfermera')
        self.doctor = account('hc-doctor@example.invalid', 'medico')
        self.admin = account('hc-admin@example.invalid', 'administrador', is_superuser=True)
        self.patient = register_patient(actor=self.nurse, data=personal_data(cedula='DEMO-8001', pnf='PNF FICTICIO',
            lugar_nacimiento='Coro', parentesco_emergencia='Hermana ficticia', telefono_emergencia='0000000001'))
        login_as(self.client, self.doctor)

    def started(self):
        attention = register_arrival(actor=self.nurse, patient_id=self.patient.pk, arrival=timezone.now(), reason='Ficticio')
        return transition_attention(actor=self.nurse, attention_id=attention.pk, target='en_atencion', expected_version=0)

    def complete(self, **changes):
        attention = self.started()
        return create_history(actor=self.doctor, patient_id=self.patient.pk, attention_id=attention.pk,
                              data={**CLINICAL, **changes})

    def pdf(self, history, actor=None):
        return clinical_history_pdf(actor=actor or self.doctor, history_id=history.pk)

    def text(self, history):
        return PdfReader(BytesIO(self.pdf(history))).pages[0].extract_text()

    def test_one_a4_portrait_page_selectable_text_logo_and_institutional_fields_only(self):
        history = self.complete()
        reader = PdfReader(BytesIO(self.pdf(history)))
        self.assertEqual(len(reader.pages), 1)
        page = reader.pages[0]
        self.assertAlmostEqual(float(page.mediabox.width), 595.2756, places=2)
        self.assertAlmostEqual(float(page.mediabox.height), 841.8898, places=2)
        self.assertEqual(len(page.images), 1)
        text = page.extract_text()
        for expected in ['FOR-SSS-04', 'HISTORIA CLÍNICA', 'LUGAR Y FECHA DE NACIMIENTO:',
                         'PARENTESCO:', 'ENFERMEDAD ACTUAL', 'DIAGNÓSTICO PROVISIONAL',
                         'DEMO-8001', 'Ficticio, Paciente', '15/01/2026', '01/01/2000', 'Coro',
                         'Hermana ficticia', '0000000001', 'PNF FICTICIO', 'Dirección ficticia',
                         *[CLINICAL[code] for code in ['motivo_consulta', 'enfermedad_actual', 'diagnostico_provisional']]]:
            self.assertIn(expected, text)
        for excluded in ['ESCUDO', 'Transcripción', 'TRATAMIENTO', 'OBSERVACIONES',
                         CLINICAL['diagnostico'], CLINICAL['tratamiento'], CLINICAL['observaciones']]:
            self.assertNotIn(excluded, text)

    def test_age_is_at_consultation_date_not_stored_age_or_current_date(self):
        history = self.complete()
        Estudiante.objects.filter(pk=self.patient.pk).update(edad=99, fecha_nacimiento=date(2000, 5, 8))
        self.assertIn('25', self.text(history))
        self.assertNotIn('99', self.text(history))

    def test_each_consultation_uses_its_own_clinical_content(self):
        first = self.complete()
        second = self.complete(motivo_consulta='SEGUNDA CONSULTA', enfermedad_actual='SEGUNDA ENFERMEDAD',
                               diagnostico_provisional='SEGUNDO PROVISIONAL')
        self.assertNotIn('SEGUNDA CONSULTA', self.text(first))
        self.assertIn('SEGUNDA CONSULTA', self.text(second))
        self.assertNotIn(CLINICAL['enfermedad_actual'], self.text(second))
        self.assertEqual(HistoriaClinica.objects.count(), 2)

    def test_doctor_http_creation_saves_new_fields_and_audit(self):
        attention = self.started()
        response = self.client.post(reverse('consulta_medica', args=[attention.pk]), CLINICAL)
        self.assertEqual(response.status_code, 302)
        history = HistoriaClinica.objects.get()
        self.assertEqual(history.enfermedad_actual, CLINICAL['enfermedad_actual'])
        self.assertEqual(history.diagnostico_provisional, CLINICAL['diagnostico_provisional'])
        event = history.cambios_clinicos.get()
        self.assertEqual(event.nuevos['enfermedad_actual'], CLINICAL['enfermedad_actual'])
        self.assertEqual(event.nuevos['diagnostico_provisional'], CLINICAL['diagnostico_provisional'])
        self.assertEqual(event.usuario, self.doctor)

    def test_correcting_new_clinical_fields_requires_reason_and_preserves_before_after(self):
        history = self.complete()
        with self.assertRaises(ValidationError):
            correct_history(actor=self.doctor, history_id=history.pk, data={'enfermedad_actual': 'Cambio'}, reason='', expected_version=0)
        response = self.client.post(reverse('corregir_historia', args=[history.pk]),
            {**CLINICAL, 'enfermedad_actual': 'Enfermedad corregida', 'diagnostico_provisional': 'Provisional corregido',
             'reason': 'Revisión clínica ficticia', 'expected_version': 0})
        self.assertEqual(response.status_code, 302)
        history.refresh_from_db()
        event = history.cambios_clinicos.first()
        self.assertEqual(event.anteriores, {code: CLINICAL[code] for code in ['enfermedad_actual', 'diagnostico_provisional']})
        self.assertEqual(event.nuevos, {'enfermedad_actual': 'Enfermedad corregida', 'diagnostico_provisional': 'Provisional corregido'})
        self.assertEqual(event.usuario, self.doctor)
        self.assertEqual(event.motivo, 'Revisión clínica ficticia')
        self.assertIsNotNone(event.fecha)
        self.assertEqual(history.version, 1)
        self.assertIn('Provisional corregido', self.text(history))

    def test_audit_failure_and_stale_version_do_not_overwrite_clinical_information(self):
        history = self.complete()
        with patch('Hisotria_clinica.services.AuditoriaClinica.objects.create', side_effect=RuntimeError('Synthetic')):
            with self.assertRaises(RuntimeError):
                correct_history(actor=self.doctor, history_id=history.pk, data={'enfermedad_actual': 'Cambio'}, reason='Ficticio', expected_version=0)
        history.refresh_from_db()
        self.assertEqual(history.enfermedad_actual, CLINICAL['enfermedad_actual'])
        self.assertEqual(history.version, 0)
        with self.assertRaises(ValidationError):
            correct_history(actor=self.doctor, history_id=history.pk, data={'diagnostico_provisional': 'Cambio'}, reason='Ficticio', expected_version=10)

    def test_nurse_and_admin_can_read_new_fields_but_cannot_write_or_export(self):
        history = self.complete()
        attention = self.started()
        for user in [self.nurse, self.admin]:
            login_as(self.client, user)
            detail = self.client.get(reverse('detalle_historia', args=[history.pk]))
            self.assertContains(detail, CLINICAL['enfermedad_actual'])
            self.assertNotContains(detail, reverse('historia_pdf', args=[history.pk]))
            for route in ['historia_pdf', 'imprimir_historia']:
                self.assertEqual(self.client.get(reverse(route, args=[history.pk])).status_code, 403)
            for route, pk in [('consulta_medica', attention.pk), ('corregir_historia', history.pk)]:
                self.assertEqual(self.client.post(reverse(route, args=[pk]),
                    {**CLINICAL, 'reason': 'Ficticio', 'expected_version': 0}).status_code, 403)
            with self.assertRaises(PermissionDenied):
                self.pdf(history, actor=user)
            with self.assertRaises(PermissionDenied):
                correct_history(actor=user, history_id=history.pk, data={'enfermedad_actual': 'Inyección'}, reason='Ficticio', expected_version=0)

    def test_pdf_rechecks_approval_and_activation_in_service_and_http(self):
        history = self.complete()
        for user in [account('hc-pending@example.invalid', 'medico', 'pendiente'),
                     account('hc-rejected@example.invalid', 'medico', 'rechazado')]:
            login_as(self.client, user)
            self.assertEqual(self.client.get(reverse('historia_pdf', args=[history.pk])).status_code, 403)
            with self.assertRaises(PermissionDenied):
                self.pdf(history, actor=user)
        self.doctor.is_active = False
        self.doctor.save(update_fields=['is_active'])
        with self.assertRaises(PermissionDenied):
            self.pdf(history)

    def test_pdf_headers_download_print_and_get_only_endpoints(self):
        history = self.complete()
        url = reverse('historia_pdf', args=[history.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF-'))
        self.assertTrue(response['Content-Disposition'].startswith('inline'))
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(response['X-Frame-Options'], 'SAMEORIGIN')
        self.assertTrue(self.client.get(url, {'download': '1'})['Content-Disposition'].startswith('attachment'))
        self.assertEqual(self.client.head(url).status_code, 200)
        self.assertEqual(self.client.post(url, {}).status_code, 405)
        self.assertEqual(self.client.get(reverse('imprimir_historia', args=[history.pk])).status_code, 200)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_unknown_history_is_404_without_leaking_clinical_data(self):
        for route in ['historia_pdf', 'imprimir_historia']:
            self.assertEqual(self.client.get(reverse(route, args=[999999])).status_code, 404)
        login_as(self.client, self.nurse)
        self.assertEqual(self.client.get(reverse('historia_pdf', args=[999999])).status_code, 403)

    def test_missing_or_blank_clinical_fields_block_emission_not_consultation_preservation(self):
        history = self.complete()
        for code in ['motivo_consulta', 'enfermedad_actual', 'diagnostico_provisional', 'diagnostico', 'tratamiento']:
            with self.subTest(code=code):
                HistoriaClinica.objects.filter(pk=history.pk).update(**{code: '   '})
                with self.assertRaisesMessage(ValidationError, 'Faltan'):
                    self.pdf(history)
                self.assertEqual(self.client.get(reverse('historia_pdf', args=[history.pk])).status_code, 422)
                HistoriaClinica.objects.filter(pk=history.pk).update(**{code: CLINICAL[code]})
        self.assertEqual(HistoriaClinica.objects.count(), 1)

    def test_missing_patient_identity_and_recorded_doctor_block_emission(self):
        history = self.complete()
        Estudiante.objects.filter(pk=self.patient.pk).update(cedula='')
        with self.assertRaisesMessage(ValidationError, 'cédula'):
            self.pdf(history)
        Estudiante.objects.filter(pk=self.patient.pk).update(cedula='DEMO-8001')
        HistoriaClinica.objects.filter(pk=history.pk).update(medico=None)
        with self.assertRaisesMessage(ValidationError, 'médico responsable'):
            self.pdf(history)

    def test_birth_date_after_consultation_or_future_consultation_is_rejected(self):
        history = self.complete()
        HistoriaClinica.objects.filter(pk=history.pk).update(fecha_consulta=date(1999, 1, 1))
        with self.assertRaisesMessage(ValidationError, 'fechas'):
            self.pdf(history)
        HistoriaClinica.objects.filter(pk=history.pk).update(fecha_consulta=timezone.localdate(timezone=REPORT_ZONE)+timedelta(days=1))
        with self.assertRaisesMessage(ValidationError, 'fechas'):
            self.pdf(history)

    def test_inconsistent_attention_patient_or_state_is_rejected(self):
        history = self.complete()
        Atencion.objects.filter(pk=history.atencion_id).update(estado='pendiente')
        with self.assertRaisesMessage(ValidationError, 'atención relacionada'):
            self.pdf(history)
        Atencion.objects.filter(pk=history.atencion_id).update(estado='atendido')
        other = register_patient(actor=self.nurse, data=personal_data(cedula='DEMO-8002'))
        HistoriaClinica.objects.filter(pk=history.pk).update(estudiante=other)
        with self.assertRaisesMessage(ValidationError, 'atención relacionada'):
            self.pdf(history)

    def test_optional_personal_fields_remain_blank_without_reusing_patient_phone(self):
        history = self.complete()
        Estudiante.objects.filter(pk=self.patient.pk).update(lugar_nacimiento='', parentesco_emergencia='', telefono_emergencia='')
        text = self.text(history)
        self.assertNotIn('Coro', text)
        self.assertNotIn('Hermana ficticia', text)
        self.assertNotIn('0000000001', text)
        self.assertEqual(text.count(self.patient.telefono), 1)

    def test_pnf_only_for_current_students_and_not_required_for_other_categories(self):
        history = self.complete()
        for category in Estudiante.Tipo.values:
            Estudiante.objects.filter(pk=self.patient.pk).update(tipo_paciente=category)
            text = self.text(history)
            self.assertEqual('PNF FICTICIO' in text, category == 'estudiante')
        Estudiante.objects.filter(pk=self.patient.pk).update(tipo_paciente=None)
        self.assertNotIn('PNF FICTICIO', self.text(history))

    def test_legacy_fields_are_not_inferred_from_diagnosis_or_observations(self):
        history = HistoriaClinica.objects.create(estudiante=self.patient, medico=self.doctor,
            fecha_consulta=date(2026, 1, 15), motivo_consulta='Ficticio', diagnostico='Diagnóstico anterior',
            tratamiento='Anterior', observaciones='No es enfermedad actual')
        self.assertEqual(history.enfermedad_actual, '')
        self.assertEqual(history.diagnostico_provisional, '')
        with self.assertRaisesMessage(ValidationError, 'enfermedad actual'):
            self.pdf(history)
        corrected = correct_history(actor=self.doctor, history_id=history.pk,
            data={'enfermedad_actual': 'Revisión explícita', 'diagnostico_provisional': 'Provisional explícito'},
            reason='Revisión médica ficticia', expected_version=0)
        self.assertIn('Provisional explícito', self.text(corrected))
        self.assertEqual(corrected.diagnostico, 'Diagnóstico anterior')
        self.assertIsNone(corrected.atencion_id)

    def test_long_sections_and_personal_fields_are_blocked_without_truncation(self):
        history = self.complete()
        for code in ['motivo_consulta', 'enfermedad_actual', 'diagnostico_provisional']:
            HistoriaClinica.objects.filter(pk=history.pk).update(**{code: 'Texto muy extenso. '*200})
            with self.assertRaisesMessage(ValidationError, 'No se ha recortado'):
                self.pdf(history)
            for route in ['historia_pdf', 'imprimir_historia']:
                self.assertEqual(self.client.get(reverse(route, args=[history.pk])).status_code, 422)
            HistoriaClinica.objects.filter(pk=history.pk).update(**{code: CLINICAL[code]})
        Estudiante.objects.filter(pk=self.patient.pk).update(lugar_nacimiento='Ciudad ficticia muy extensa. '*4)
        with self.assertRaisesMessage(ValidationError, 'Lugar y fecha'):
            self.pdf(history)

    def test_text_is_escaped_and_preserves_literal_tags_and_accents(self):
        history = self.complete(enfermedad_actual='Descripción <b>literal</b> & ficticia, con ñ y á.')
        self.assertIn('Descripción <b>literal</b> & ficticia, con ñ y á.', self.text(history))

    def test_section_capacity_preserves_three_five_three_lines_and_rejects_one_more(self):
        sections = {'motivo_consulta': ('Muestra M', 3), 'enfermedad_actual': ('Muestra E', 5),
                    'diagnostico_provisional': ('Muestra P', 3)}
        values = {code: '\n'.join(f'{prefix} {index+1}' for index in range(count))
                  for code, (prefix, count) in sections.items()}
        history = self.complete(**values)
        text = self.text(history)
        for prefix, count in sections.values():
            for index in range(count):
                self.assertIn(f'{prefix} {index+1}', text)
        self.assertEqual(len(PdfReader(BytesIO(self.pdf(history))).pages), 1)
        for code in sections:
            HistoriaClinica.objects.filter(pk=history.pk).update(**{code: values[code]+'\nUna línea adicional'})
            with self.assertRaisesMessage(ValidationError, 'No se ha recortado'):
                self.pdf(history)
            HistoriaClinica.objects.filter(pk=history.pk).update(**{code: values[code]})

    def test_new_personal_fields_are_optional_registered_and_audited(self):
        patient = register_patient(actor=self.nurse, data=personal_data(cedula='DEMO-8010'))
        self.assertEqual((patient.lugar_nacimiento, patient.parentesco_emergencia, patient.telefono_emergencia), ('', '', ''))
        login_as(self.client, self.nurse)
        response = self.client.post(reverse('editar_paciente', args=[patient.pk]),
            personal_data(cedula=patient.cedula, lugar_nacimiento='Coro', parentesco_emergencia='Familiar', telefono_emergencia='0000000002'))
        self.assertEqual(response.status_code, 302)
        event = patient.cambios_personales.filter(accion='modificacion').get()
        self.assertEqual(event.anteriores, {'lugar_nacimiento': '', 'parentesco_emergencia': '', 'telefono_emergencia': ''})
        self.assertEqual(event.nuevos, {'lugar_nacimiento': 'Coro', 'parentesco_emergencia': 'Familiar', 'telefono_emergencia': '0000000002'})
        self.assertEqual(event.usuario, self.nurse)
        self.assertIsNotNone(event.fecha)

    def test_patient_services_reject_clinical_field_injection_and_admin_personal_edits(self):
        with self.assertRaises(ValidationError):
            update_patient(actor=self.nurse, patient_id=self.patient.pk,
                data={'tipo_paciente': 'estudiante', 'enfermedad_actual': 'No permitido'})
        with self.assertRaises(PermissionDenied):
            update_patient(actor=self.admin, patient_id=self.patient.pk, data={'tipo_paciente': 'estudiante', 'lugar_nacimiento': 'Cambio'})
        self.assertFalse(EstudianteForm(data=personal_data(telefono_emergencia='x'*21)).is_valid())

    def test_generating_pdf_does_not_modify_sources_audits_or_versions(self):
        history = self.complete()
        before = (list(HistoriaClinica.objects.values()), list(Estudiante.objects.values()),
                  list(AuditoriaClinica.objects.values()), list(AuditoriaPaciente.objects.values()))
        with CaptureQueriesContext(connection) as queries:
            self.pdf(history)
        self.assertFalse([q for q in queries if q['sql'].lstrip().upper().startswith(('INSERT ', 'UPDATE ', 'DELETE ', 'CREATE ', 'ALTER '))])
        self.assertEqual(before, (list(HistoriaClinica.objects.values()), list(Estudiante.objects.values()),
                         list(AuditoriaClinica.objects.values()), list(AuditoriaPaciente.objects.values())))

    def test_new_clinical_fields_remain_csrf_protected(self):
        attention = self.started()
        client = Client(enforce_csrf_checks=True)
        login_as(client, self.doctor)
        self.assertEqual(client.post(reverse('consulta_medica', args=[attention.pk]), CLINICAL).status_code, 403)
