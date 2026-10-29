from datetime import date, datetime, timezone as datetime_timezone
from io import BytesIO
import re
from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfReader

from LoginRegister.test_security import account, login_as
from .daily_options import OPTION_CODES
from .forms import HistoriaClinicaForm
from .models import Atencion, AuditoriaClinica, HistoriaClinica
from .pdf_reports import daily_register_pdf
from .services import correct_history, create_history, register_arrival, register_patient, transition_attention
from .test_patients import personal_data


CLINICAL = dict(fecha_consulta=date(2026, 1, 15), motivo_consulta='Motivo ficticio',
                diagnostico='Diagnóstico ficticio', tratamiento='Texto ficticio', observaciones='')


def pdf_row_numbers(page):
    rows = []
    def visitor(text, cm, tm, font, size):
        x = tm[4]*cm[0] + tm[5]*cm[2] + cm[4]
        if 32 < x < 58 and re.fullmatch(r'\d{2}', text.strip()):
            rows.append(text.strip())
    page.extract_text(visitor_text=visitor)
    return rows


class DailyOptionsTests(TestCase):
    def setUp(self):
        self.nurse = account('options-nurse@example.invalid', 'enfermera')
        self.doctor = account('options-doctor@example.invalid', 'medico')
        self.admin = account('options-admin@example.invalid', 'administrador', is_superuser=True)
        self.patient = register_patient(actor=self.nurse, data=personal_data(nombre='Persona', apellido='Ficticia', cedula='DEMO-7001'))
        login_as(self.client, self.doctor)

    def started(self):
        attention = register_arrival(actor=self.nurse, patient_id=self.patient.pk, arrival=timezone.now(), reason='Ficticio')
        return transition_attention(actor=self.nurse, attention_id=attention.pk, target='en_atencion', expected_version=0)

    def complete(self, **options):
        attention = self.started()
        history = create_history(actor=self.doctor, patient_id=self.patient.pk, attention_id=attention.pk,
                                 data={**CLINICAL, **options})
        Atencion.objects.filter(pk=attention.pk).update(actualizada_en=datetime(2026, 1, 15, 12, tzinfo=datetime_timezone.utc))
        return history

    def pdf(self, start=date(2026, 1, 15), end=date(2026, 1, 15), actor=None):
        return daily_register_pdf(actor=actor or self.doctor, start=start, end=end)

    def reader(self, **kwargs):
        return PdfReader(BytesIO(self.pdf(**kwargs)))

    def test_eight_optional_checkboxes_with_exact_labels_and_two_fieldsets(self):
        attention = self.started()
        response = self.client.get(reverse('consulta_medica', args=[attention.pk]))
        self.assertContains(response, '<fieldset', count=2)
        for code, label in zip(OPTION_CODES, ['RP', 'T de C', 'Tto', 'Lab', 'Ref', 'Imag', 'Rx', 'Cit']):
            field = response.context['form'].fields[code]
            self.assertEqual(field.label, label)
            self.assertFalse(field.required)
            self.assertContains(response, f'type="checkbox" name="{code}"')
        self.assertContains(response, 'Datos adicionales del Registro Médico Diario')
        self.assertContains(response, 'Estudios y procedimientos solicitados')

    def test_no_options_required_and_clinical_text_does_not_select_tto(self):
        history = self.complete()
        self.assertTrue(history.tratamiento)
        self.assertEqual([getattr(history, code) for code in OPTION_CODES], [False]*8)
        self.assertEqual([history.cambios_clinicos.get().nuevos[code] for code in OPTION_CODES], [False]*8)

    def test_each_option_is_independent_and_multiple_options_are_preserved(self):
        for code in OPTION_CODES:
            history = self.complete(**{code: True})
            self.assertEqual([name for name in OPTION_CODES if getattr(history, name)], [code])
        history = self.complete(rp=True, t_de_c=True, lab=True, cit=True)
        self.assertEqual([code for code in OPTION_CODES if getattr(history, code)], ['rp', 't_de_c', 'lab', 'cit'])
        self.assertEqual(history.diagnostico, CLINICAL['diagnostico'])

    def test_http_creation_and_correction_allow_selection_and_clearing(self):
        attention = self.started()
        self.assertEqual(self.client.post(reverse('consulta_medica', args=[attention.pk]),
            {**CLINICAL, 'rp': 'on', 'rx': 'on'}).status_code, 302)
        history = HistoriaClinica.objects.get()
        form = self.client.get(reverse('corregir_historia', args=[history.pk])).context['form']
        self.assertTrue(form['rp'].value())
        self.assertTrue(form['rx'].value())
        before = history.cambios_clinicos.count()
        response = self.client.post(reverse('corregir_historia', args=[history.pk]),
            {**CLINICAL, 't_de_c': 'on', 'expected_version': 0, 'reason': 'Corrección ficticia'})
        self.assertEqual(response.status_code, 302)
        history.refresh_from_db()
        self.assertFalse(history.rp)
        self.assertFalse(history.rx)
        self.assertTrue(history.t_de_c)
        self.assertEqual(history.cambios_clinicos.count(), before+1)
        audit = history.cambios_clinicos.first()
        self.assertEqual(audit.anteriores, {'rp': True, 'rx': True, 't_de_c': False})
        self.assertEqual(audit.nuevos, {'rp': False, 'rx': False, 't_de_c': True})
        self.assertEqual(audit.usuario, self.doctor)
        self.assertIsNotNone(audit.fecha)

    def test_service_rejects_strings_integers_none_and_unknown_codes(self):
        history = self.complete()
        for value in ['X', 'false', 'on', 0, 1, None, []]:
            with self.assertRaises(ValidationError):
                correct_history(actor=self.doctor, history_id=history.pk, data={'rp': value},
                                reason='Ficticio', expected_version=0)
        with self.assertRaises(ValidationError):
            correct_history(actor=self.doctor, history_id=history.pk, data={'RP': True}, reason='Ficticio', expected_version=0)
        attention = self.started()
        with self.assertRaises(ValidationError):
            create_history(actor=self.doctor, patient_id=self.patient.pk, attention_id=attention.pk, data={**CLINICAL, 'lab': 'yes'})

    def test_reason_is_required_and_stale_corrections_are_rejected(self):
        history = self.complete(rp=True)
        with self.assertRaises(ValidationError):
            correct_history(actor=self.doctor, history_id=history.pk, data={'rp': False}, reason=' ', expected_version=0)
        correct_history(actor=self.doctor, history_id=history.pk, data={'rp': False}, reason='Revisión ficticia', expected_version=0)
        with self.assertRaises(ValidationError):
            correct_history(actor=self.doctor, history_id=history.pk, data={'lab': True}, reason='Ficticio', expected_version=0)
        history.refresh_from_db()
        self.assertFalse(history.lab)

    def test_failed_audit_rolls_back_selection_and_version(self):
        history = self.complete()
        with patch('Hisotria_clinica.services.AuditoriaClinica.objects.create', side_effect=RuntimeError('Synthetic')):
            with self.assertRaises(RuntimeError):
                correct_history(actor=self.doctor, history_id=history.pk, data={'rp': True}, reason='Ficticio', expected_version=0)
        history.refresh_from_db()
        self.assertFalse(history.rp)
        self.assertEqual(history.version, 0)

    def test_partial_legacy_correction_does_not_convert_other_unknown_options(self):
        history = HistoriaClinica.objects.create(estudiante=self.patient, **CLINICAL)
        correct_history(actor=self.doctor, history_id=history.pk, data={'rp': True}, reason='Verificación ficticia', expected_version=0)
        history.refresh_from_db()
        self.assertIsNone(history.lab)
        self.assertEqual(history.cambios_clinicos.get().anteriores, {'rp': None})
        self.assertEqual(history.cambios_clinicos.get().nuevos, {'rp': True})

    def test_label_changes_do_not_change_codes_or_stored_selections(self):
        history = self.complete(lab=True)
        with patch('Hisotria_clinica.forms.OPTION_GROUPS', [('Grupo', [('lab', 'Etiqueta futura')])]):
            form = HistoriaClinicaForm(instance=history)
            self.assertTrue(form['lab'].value())
            self.assertEqual(form.fields['lab'].label, 'Etiqueta futura')
        history.refresh_from_db()
        self.assertTrue(history.lab)

    def test_nurse_admin_pending_and_technical_superuser_cannot_write_selections(self):
        history = self.complete()
        attention = self.started()
        pending = account('options-pending@example.invalid', 'medico', 'pendiente')
        for user in [self.nurse, self.admin, pending]:
            login_as(self.client, user)
            self.assertEqual(self.client.post(reverse('consulta_medica', args=[attention.pk]), {**CLINICAL, 'lab': 'on'}).status_code, 403)
            self.assertEqual(self.client.post(reverse('corregir_historia', args=[history.pk]),
                {**CLINICAL, 'lab': 'on', 'reason': 'Ficticio', 'expected_version': 0}).status_code, 403)
            with self.assertRaises(PermissionDenied):
                correct_history(actor=user, history_id=history.pk, data={'lab': True}, reason='Ficticio', expected_version=0)
        history.refresh_from_db()
        self.assertFalse(history.lab)

    def test_read_only_roles_see_selections_without_editable_checkboxes(self):
        history = self.complete(rp=True)
        for user in [self.nurse, self.admin]:
            login_as(self.client, user)
            response = self.client.get(reverse('detalle_historia', args=[history.pk]))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, '<dd>X</dd>', html=True)
            self.assertNotContains(response, 'type="checkbox"')

    def test_pdf_places_eight_x_marks_in_the_reference_columns(self):
        self.complete(**dict.fromkeys(OPTION_CODES, True))
        page = self.reader().pages[0]
        marks = []
        def visitor(text, cm, tm, font, size):
            if text.strip() == 'X':
                marks.append((tm[4]*cm[0] + tm[5]*cm[2] + cm[4], tm[4]*cm[1] + tm[5]*cm[3] + cm[5]))
        page.extract_text(visitor_text=visitor)
        # Independent column boundaries from the supplied reference, not the renderer mapping.
        bounds = [(58, 85), (379, 407), (630, 660.5), (660.5, 690.4),
                  (690.4, 720.3), (720.3, 750.2), (750.2, 780.1), (780.1, 810)]
        self.assertEqual(len(marks), 8)
        for left, right in bounds:
            self.assertEqual(sum(left < x < right for x, y in marks), 1)
        self.assertTrue(all(320 < y < 335 for x, y in marks))

    def test_unselected_and_unknown_options_produce_no_x_and_no_clinical_inference(self):
        history = self.complete()
        HistoriaClinica.objects.filter(pk=history.pk).update(rp=None, lab=None)
        text = self.reader().pages[0].extract_text()
        self.assertNotIn('\nX\n', text)
        self.assertIn('Diagnóstico ficticio', text)
        self.assertNotIn(CLINICAL['tratamiento'], text)

    def test_pdf_preserves_code_headers_a4_orientation_logo_and_selectable_patient_data(self):
        self.complete(rp=True)
        page = self.reader().pages[0]
        self.assertAlmostEqual(float(page.mediabox.width), 841.8898, places=2)
        self.assertAlmostEqual(float(page.mediabox.height), 595.2756, places=2)
        text = page.extract_text()
        for value in ['FOR-SSS-02', 'REGISTRO MÉDICO DIARIO', 'Especialidad', 'T.C.', 'Tto', 'Lab', 'Ref', 'Imag', 'Rx', 'Cit', 'DEMO-7001', 'Ficticia, Persona']:
            self.assertIn(value, text)
        self.assertNotIn('ESCUDO', text)
        self.assertEqual(len(page.images), 1)
        self.assertEqual(pdf_row_numbers(page), [f'{i:02}' for i in range(1, 18)])

    def test_pdf_paginates_17_rows_and_keeps_each_visit_once_at_boundaries(self):
        for count in [17, 18, 34, 35]:
            with self.subTest(count=count):
                for _ in range(count-HistoriaClinica.objects.count()):
                    self.complete()
                reader = self.reader()
                self.assertEqual(len(reader.pages), (count+16)//17)
                texts = [page.extract_text() for page in reader.pages]
                self.assertEqual(sum(text.count('DEMO-7001') for text in texts), count)
                self.assertTrue(all(text.count('FOR-SSS-02') == 1 for text in texts))
                self.assertTrue(all(pdf_row_numbers(page) == [f'{i:02}' for i in range(1, 18)] for page in reader.pages))

    def test_pdf_date_range_keeps_empty_dates_and_explicit_teams_separate(self):
        self.complete()
        other = self.complete()
        Atencion.objects.filter(pk=other.atencion_id).update(turno='Tarde')
        reader = self.reader(start=date(2026, 1, 14), end=date(2026, 1, 16))
        self.assertEqual(len(reader.pages), 4)
        dates = [re.search(r'\d{2}/\d{2}/\d{4}', page.extract_text()).group() for page in reader.pages]
        self.assertEqual(dates, ['14/01/2026', '15/01/2026', '15/01/2026', '16/01/2026'])

    def test_pdf_after_correction_uses_new_selection_without_moving_completion_date(self):
        history = self.complete(rp=True)
        correct_history(actor=self.doctor, history_id=history.pk, data={'rp': False, 'lab': True}, reason='Ficticio', expected_version=0)
        self.assertEqual(len(self.reader().pages), 1)
        self.assertEqual(history.cambios_clinicos.count(), 2)
        from .reports import daily_report
        row = daily_report(actor=self.nurse, start=date(2026, 1, 15), end=date(2026, 1, 15)).days[0].teams[0].rows[0]
        self.assertEqual([option['code'] for option in row['options'] if option['selected']], ['lab'])

    def test_pdf_blocks_long_text_and_invalid_completed_data_without_truncation(self):
        history = self.complete()
        HistoriaClinica.objects.filter(pk=history.pk).update(diagnostico='Texto muy largo. '*100)
        with self.assertRaisesMessage(ValidationError, 'No se ha recortado'):
            self.pdf()
        response = self.client.get(reverse('registro_diario_pdf'), {'fecha': '2026-01-15'})
        self.assertEqual(response.status_code, 422)
        self.assertContains(response, 'No se ha recortado', status_code=422)
        self.assertEqual(self.client.get(reverse('imprimir_registro_diario'), {'fecha': '2026-01-15'}).status_code, 422)
        HistoriaClinica.objects.filter(pk=history.pk).update(diagnostico='')
        with self.assertRaisesMessage(ValidationError, 'inconsistentes'):
            self.pdf()

    def test_pdf_http_permissions_private_headers_download_and_print_routes(self):
        self.complete()
        for user in [self.nurse, self.doctor]:
            login_as(self.client, user)
            response = self.client.get(reverse('registro_diario_pdf'), {'fecha': '2026-01-15'})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.content.startswith(b'%PDF-'))
            self.assertEqual(response['Content-Type'], 'application/pdf')
            self.assertTrue(response['Content-Disposition'].startswith('inline'))
            self.assertEqual(response['X-Frame-Options'], 'SAMEORIGIN')
            self.assertIn('no-store', response['Cache-Control'])
            self.assertTrue(self.client.get(reverse('registro_diario_pdf'), {'fecha': '2026-01-15', 'download': '1'})['Content-Disposition'].startswith('attachment'))
            self.assertEqual(self.client.get(reverse('imprimir_registro_diario'), {'fecha': '2026-01-15'}).status_code, 200)
            self.assertEqual(self.client.post(reverse('registro_diario_pdf'), {}).status_code, 405)
        for user in [self.admin, account('pdf-pending@example.invalid', 'medico', 'pendiente')]:
            login_as(self.client, user)
            for route in ['registro_diario_pdf', 'imprimir_registro_diario']:
                self.assertEqual(self.client.get(reverse(route)).status_code, 403)
            with self.assertRaises(PermissionDenied):
                self.pdf(actor=user)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('registro_diario_pdf')).status_code, 302)

    def test_invalid_pdf_ranges_are_errors_not_silent_default_reports(self):
        for query in [{'fecha': 'bad'}, {'desde': '2026-01-15'}, {'desde': '2026-01-16', 'hasta': '2026-01-15'},
                      {'desde': '2024-01-01', 'hasta': '2026-01-15'}]:
            for route in ['registro_diario_pdf', 'imprimir_registro_diario']:
                self.assertEqual(self.client.get(reverse(route), query).status_code, 400)

    def test_pdf_rendering_is_read_only(self):
        self.complete(lab=True)
        with CaptureQueriesContext(connection) as queries:
            self.pdf()
        self.assertFalse([q for q in queries if q['sql'].lstrip().upper().startswith(('INSERT ', 'UPDATE ', 'DELETE ', 'CREATE ', 'ALTER '))])
