"""Cross-document review and regressions found during the Phase 2 audit."""
from datetime import date, datetime, timezone as utc_timezone
from io import BytesIO
import hashlib
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import connection, IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfReader

from LoginRegister.test_security import account, login_as
from .models import Atencion, AuditoriaClinica, ConstanciaReposo, HistoriaClinica
from .pdf_histories import clinical_history_pdf
from .pdf_reports import daily_register_pdf
from .reposos import approve_reposo, create_reposo_draft, issued_reposo_pdf, review_reposo
from .services import create_history, correct_history, register_arrival, register_patient, transition_attention
from .test_patients import personal_data


class Phase2IntegrationTests(TestCase):
    def setUp(self):
        self.doctor = account('audit-doctor@example.invalid', 'medico')
        self.patient = register_patient(actor=self.doctor, data=personal_data(cedula='DEMO-9901'))
        self.clinical = dict(fecha_consulta=date(2026, 1, 15), motivo_consulta='Motivo ficticio',
            diagnostico='Diagnóstico ficticio', tratamiento='Tratamiento ficticio',
            enfermedad_actual='Enfermedad ficticia', diagnostico_provisional='Provisional ficticio')
        login_as(self.client, self.doctor)

    def started(self):
        record = register_arrival(actor=self.doctor, patient_id=self.patient.pk, arrival=timezone.now(), reason='Ficticio')
        return transition_attention(actor=self.doctor, attention_id=record.pk, target='en_atencion', expected_version=0)

    def complete(self):
        attention = self.started()
        return create_history(actor=self.doctor, patient_id=self.patient.pk, attention_id=attention.pk, data=self.clinical)

    def draft(self, history):
        return create_reposo_draft(actor=self.doctor, history_id=history.pk,
            data={'motivo_reposo': 'Motivo ficticio', 'dias': 2, 'fecha_inicio': date(2026, 1, 15)})

    def approve(self, record):
        _, _, _, token = review_reposo(actor=self.doctor, reposo_id=record.pk)
        return approve_reposo(actor=self.doctor, reposo_id=record.pk, expected_revision=0, review_token=token, confirmed=True)

    def replace_sql(self, issued, *, new_id=False):
        columns = [field.column for field in ConstanciaReposo._meta.concrete_fields]
        quoted = [connection.ops.quote_name(name) for name in columns]
        projection = [('NULL' if new_id and name == 'id' else '%s' if name in ['pdf', 'pdf_sha256'] else quoted[index])
                      for index, name in enumerate(columns)]
        payload = b'FICTICIO: no debe reemplazar una version emitida'
        with connection.cursor() as cursor:
            cursor.execute(f'INSERT OR REPLACE INTO "Hisotria_clinica_constanciareposo" ({", ".join(quoted)}) '
                           f'SELECT {", ".join(projection)} FROM "Hisotria_clinica_constanciareposo" WHERE id = %s',
                           [payload, hashlib.sha256(payload).hexdigest(), issued.pk])

    def test_sql_replace_cannot_overwrite_an_emitted_primary_key(self):
        issued = self.approve(self.draft(self.complete()))
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.replace_sql(issued)

    def test_sql_replace_cannot_recreate_an_emitted_unique_version_with_another_id(self):
        issued = self.approve(self.draft(self.complete()))
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.replace_sql(issued, new_id=True)

    def test_update_or_replace_cannot_delete_an_emitted_version_as_a_conflict_victim(self):
        history = self.complete()
        issued = self.approve(self.draft(history))
        other = self.draft(self.complete())
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute('UPDATE OR REPLACE "Hisotria_clinica_constanciareposo" '
                               'SET historia_id = %s, numero_version = %s WHERE id = %s',
                               [history.pk, issued.numero_version, other.pk])

    def test_required_clinical_whitespace_does_not_finish_attention(self):
        attention = self.started()
        with self.assertRaises(ValidationError):
            create_history(actor=self.doctor, patient_id=self.patient.pk, attention_id=attention.pk,
                           data={**self.clinical, 'diagnostico': '   '})
        attention.refresh_from_db()
        self.assertEqual(attention.estado, 'en_atencion')
        self.assertEqual(HistoriaClinica.objects.count(), 0)

    def test_new_consultation_cannot_finish_with_a_future_or_prebirth_clinical_date(self):
        attention = self.started()
        for value in [date(9999, 1, 1), date(1999, 1, 1)]:
            with self.assertRaises(ValidationError):
                create_history(actor=self.doctor, patient_id=self.patient.pk, attention_id=attention.pk,
                               data={**self.clinical, 'fecha_consulta': value})

    def test_pdf_font_preserves_greek_and_subscript_clinical_text(self):
        self.clinical['enfermedad_actual'] = 'Muestra ficticia: β y CO₂, sin evaluación real.'
        history = self.complete()
        text = PdfReader(BytesIO(clinical_history_pdf(actor=self.doctor, history_id=history.pk))).pages[0].extract_text()
        self.assertIn('β', text)
        self.assertIn('CO₂', text)

    def test_pdf_rejects_unsupported_glyph_instead_of_silent_substitution(self):
        self.clinical['enfermedad_actual'] = 'Muestra ficticia '+chr(0x10FFFF)
        history = self.complete()
        with self.assertRaisesMessage(ValidationError, 'fuente'):
            clinical_history_pdf(actor=self.doctor, history_id=history.pk)

    def test_corrections_cannot_clear_required_fields_using_whitespace_or_invalid_dates(self):
        history = self.complete()
        before = list(history.cambios_clinicos.values())
        for data in [{'tratamiento': ' \n '}, {'motivo_consulta': '\t'}, {'fecha_consulta': date(9999, 1, 1)},
                     {'fecha_consulta': date(1999, 1, 1)}]:
            with self.assertRaises(ValidationError):
                correct_history(actor=self.doctor, history_id=history.pk, data=data, reason='Ensayo ficticio', expected_version=0)
        history.refresh_from_db()
        self.assertEqual(history.version, 0)
        self.assertEqual(list(history.cambios_clinicos.values()), before)

    def test_invalid_historical_dates_are_not_rewritten_by_unrelated_audited_correction(self):
        history = self.complete()
        HistoriaClinica.objects.filter(pk=history.pk).update(fecha_consulta=date(9999, 1, 1))
        correct_history(actor=self.doctor, history_id=history.pk, data={'diagnostico': 'Revisión ficticia'},
                        reason='Ensayo sobre dato histórico ficticio', expected_version=0)
        history.refresh_from_db()
        self.assertEqual(history.fecha_consulta, date(9999, 1, 1))
        with self.assertRaises(ValidationError):
            clinical_history_pdf(actor=self.doctor, history_id=history.pk)

    def test_unicode_is_preserved_in_all_three_documents_and_unsupported_characters_are_errors(self):
        self.clinical['diagnostico'] = 'β y CO₂ ficticios'
        history = self.complete()
        Atencion.objects.filter(pk=history.atencion_id).update(actualizada_en=datetime(2026, 1, 15, 12, tzinfo=utc_timezone.utc))
        daily = daily_register_pdf(actor=self.doctor, start=date(2026, 1, 15), end=date(2026, 1, 15))
        self.assertIn('β y CO₂', PdfReader(BytesIO(daily)).pages[0].extract_text())
        record = create_reposo_draft(actor=self.doctor, history_id=history.pk,
            data={'motivo_reposo': 'Muestra β y CO₂ ficticia', 'dias': 2, 'fecha_inicio': date(2026, 1, 15)})
        issued = self.approve(record)
        original = bytes(issued.pdf)
        self.assertIn('β y CO₂', PdfReader(BytesIO(original)).pages[0].extract_text())
        with patch('Hisotria_clinica.reposos.render_reposo', side_effect=AssertionError('No regenerar')):
            self.assertEqual(issued_reposo_pdf(actor=self.doctor, reposo_id=issued.pk)[1], original)
        HistoriaClinica.objects.filter(pk=history.pk).update(diagnostico='Ficticio '+chr(0x10FFFF))
        response = self.client.get(reverse('registro_diario_pdf'), {'fecha': '2026-01-15'})
        self.assertEqual(response.status_code, 422)
        self.assertContains(response, 'fuente', status_code=422)

    def test_review_token_is_invalid_after_document_template_revision_changes(self):
        record = self.draft(self.complete())
        _, _, _, token = review_reposo(actor=self.doctor, reposo_id=record.pk)
        with patch('Hisotria_clinica.reposos.TEMPLATE_REVISION', 'plantilla-distinta-para-ensayo'):
            with self.assertRaisesMessage(ValidationError, 'datos cambiaron'):
                approve_reposo(actor=self.doctor, reposo_id=record.pk, expected_revision=0, review_token=token, confirmed=True)

    def test_three_pdf_permission_matrix_and_revoked_sessions(self):
        history = self.complete()
        record = self.approve(self.draft(history))
        roles = [('medico', [200, 200, 200]), ('enfermera', [200, 403, 403]),
                 ('administrador', [403, 403, 403])]
        routes = [reverse('registro_diario_pdf'), reverse('historia_pdf', args=[history.pk]), reverse('reposo_pdf', args=[record.pk])]
        for index, (role, statuses) in enumerate(roles):
            actor = account(f'matrix-{index}@example.invalid', role, is_superuser=role == 'administrador')
            login_as(self.client, actor)
            for route, expected in zip(routes, statuses):
                self.assertEqual(self.client.get(route, {'fecha': '2026-01-15'}).status_code, expected)
            type(actor).objects.filter(pk=actor.pk).update(is_active=False)
            for route in routes:
                self.assertIn(self.client.get(route, {'fecha': '2026-01-15'}).status_code, [302, 403])
        pending = account('matrix-pending@example.invalid', 'medico', 'pendiente')
        login_as(self.client, pending)
        self.assertTrue(all(self.client.get(route).status_code == 403 for route in routes))

    def test_sql_replace_cannot_remove_emitted_successor_by_unique_previous_link(self):
        history = self.complete()
        first = self.approve(self.draft(history))
        second = create_reposo_draft(actor=self.doctor, history_id=history.pk,
            data={'motivo_reposo': 'Segunda versión ficticia', 'dias': 3, 'fecha_inicio': date(2026, 1, 15)},
            previous_id=first.pk, correction_reason='Ensayo ficticio')
        second = self.approve(second)
        other = self.draft(self.complete())
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute('UPDATE OR REPLACE "Hisotria_clinica_constanciareposo" SET anterior_id = %s WHERE id = %s',
                               [first.pk, other.pk])
        second.refresh_from_db()
        self.assertEqual(second.anterior_id, first.pk)
