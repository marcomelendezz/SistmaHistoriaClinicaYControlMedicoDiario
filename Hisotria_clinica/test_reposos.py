from datetime import date, timedelta
from io import BytesIO
import hashlib
import time
from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, IntegrityError, transaction
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfReader

from LoginRegister.test_security import account, login_as
from .models import AuditoriaClinica, ConstanciaReposo, Estudiante
from .reposos import (approve_reposo, create_reposo_draft, issued_reposo_pdf, reposos_for,
                     review_reposo, update_reposo_draft)
from .reports import REPORT_ZONE
from .services import (correct_history, create_history, register_arrival, register_patient,
                       transition_attention, update_patient)
from .test_patients import personal_data


class ReposoTests(TestCase):
    def setUp(self):
        self.doctor = account('reposo-doctor@example.invalid', 'medico')
        self.other_doctor = account('reposo-other@example.invalid', 'medico')
        self.nurse = account('reposo-nurse@example.invalid', 'enfermera')
        self.admin = account('reposo-admin@example.invalid', 'administrador', is_superuser=True)
        self.patient = register_patient(actor=self.nurse, data=personal_data(nombre='Paciente', apellido='Ficticio',
                                      cedula='DEMO-9001', pnf='PNF ficticio'))
        attention = register_arrival(actor=self.nurse, patient_id=self.patient.pk, arrival=timezone.now(), reason='Ficticio')
        transition_attention(actor=self.nurse, attention_id=attention.pk, target='en_atencion', expected_version=0)
        self.history = create_history(actor=self.doctor, patient_id=self.patient.pk, attention_id=attention.pk,
            data={'fecha_consulta': date(2026, 1, 15), 'motivo_consulta': 'Consulta ficticia',
                  'diagnostico': 'Diagnóstico ficticio', 'tratamiento': 'Tratamiento ficticio'})
        self.data = {'motivo_reposo': 'Motivo clínico ficticio', 'dias': 3, 'fecha_inicio': date(2026, 1, 15)}
        login_as(self.client, self.doctor)

    def draft(self, **kwargs):
        return create_reposo_draft(actor=self.doctor, history_id=self.history.pk, data=self.data, **kwargs)

    def approve(self, record, **kwargs):
        _, _, _, token = review_reposo(actor=self.doctor, reposo_id=record.pk)
        return approve_reposo(actor=self.doctor, reposo_id=record.pk, expected_revision=record.revision,
                              review_token=token, confirmed=True, **kwargs)

    def text(self, content):
        return PdfReader(BytesIO(content)).pages[0].extract_text()

    def test_draft_records_period_version_author_and_audit_without_definitive_pdf(self):
        record = self.draft()
        self.assertEqual(record.estado, 'borrador')
        self.assertEqual(record.numero_version, 1)
        self.assertEqual(record.fecha_fin, date(2026, 1, 17))
        self.assertEqual(record.creado_por, self.doctor)
        self.assertEqual(bytes(record.pdf), b'')
        self.assertEqual(record.datos_emitidos, {})
        self.assertIsNone(record.aprobado_en)
        event = self.history.cambios_clinicos.first()
        self.assertEqual(event.usuario, self.doctor)
        self.assertEqual(event.nuevos['constancia_reposo']['id'], record.pk)

    def test_period_includes_first_day_and_leap_day(self):
        self.data.update(fecha_inicio=date(2024, 2, 28), dias=2)
        record = self.draft()
        self.assertEqual(record.fecha_fin, date(2024, 2, 29))
        update_reposo_draft(actor=self.doctor, reposo_id=record.pk,
            data={**self.data, 'dias': 1}, expected_revision=0, reason='Revisión ficticia')
        record.refresh_from_db()
        self.assertEqual(record.fecha_fin, record.fecha_inicio)

    def test_invalid_days_dates_missing_reason_and_extra_fields_are_rejected(self):
        for changes in [{'dias': 0}, {'dias': -1}, {'dias': True}, {'dias': '3'}, {'motivo_reposo': '  '},
                        {'fecha_inicio': '2026-01-15'}, {'dias': 999999999999}, {'pdf': b'fake'}, {'aprobado_por': self.doctor}]:
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                create_reposo_draft(actor=self.doctor, history_id=self.history.pk, data={**self.data, **changes})
        self.assertEqual(ConstanciaReposo.objects.count(), 0)

    def test_preview_is_marked_and_contains_automatic_data_without_emitting_or_writing(self):
        record = self.draft()
        count = AuditoriaClinica.objects.count()
        with CaptureQueriesContext(connection) as queries:
            _, snapshot, content, token = review_reposo(actor=self.doctor, reposo_id=record.pk)
        self.assertFalse([q for q in queries if q['sql'].lstrip().upper().startswith(('INSERT ', 'UPDATE ', 'DELETE '))])
        text = self.text(content)
        for value in ['BORRADOR', 'SIN APROBACIÓN', 'FOR-SSS-07', 'Paciente Ficticio', 'DEMO-9001', 'PNF ficticio', str(self.doctor)]:
            self.assertIn(value, text)
        self.assertEqual(snapshot['medico']['id'], self.doctor.pk)
        self.assertEqual(snapshot['historia_id'], self.history.pk)
        self.assertTrue(token)
        record.refresh_from_db()
        self.assertEqual(record.estado, 'borrador')
        self.assertEqual(AuditoriaClinica.objects.count(), count)
        with self.assertRaises(ValidationError):
            issued_reposo_pdf(actor=self.doctor, reposo_id=record.pk)

    def test_explicit_approval_saves_exact_pdf_snapshot_hash_actor_and_time(self):
        record = self.approve(self.draft())
        self.assertEqual(record.estado, 'emitida')
        self.assertEqual(record.aprobado_por, self.doctor)
        self.assertIsNotNone(record.aprobado_en)
        self.assertEqual(record.datos_emitidos['fecha_emision'], timezone.localdate(timezone=REPORT_ZONE).isoformat())
        self.assertEqual(record.datos_emitidos['paciente']['cedula'], self.patient.cedula)
        self.assertEqual(hashlib.sha256(bytes(record.pdf)).hexdigest(), record.pdf_sha256)
        text = self.text(bytes(record.pdf))
        self.assertNotIn('BORRADOR', text)
        self.assertIn('CONSTANCIA DE REPOSO', text)
        event = self.history.cambios_clinicos.first()
        self.assertEqual(event.nuevos['constancia_reposo']['pdf_sha256'], record.pdf_sha256)
        self.assertEqual(event.anteriores['constancia_reposo']['estado'], 'borrador')
        page = PdfReader(BytesIO(bytes(record.pdf))).pages[0]
        self.assertAlmostEqual(float(page.mediabox.width), 595.2756, places=2)
        self.assertAlmostEqual(float(page.mediabox.height), 841.8898, places=2)
        self.assertEqual(len(page.images), 1)
        self.assertEqual(len(PdfReader(BytesIO(bytes(record.pdf))).pages), 1)

    def test_approval_requires_confirmation_valid_review_and_current_revision(self):
        record = self.draft()
        _, _, _, token = review_reposo(actor=self.doctor, reposo_id=record.pk)
        for confirmed, review, revision in [(False, token, 0), (True, 'inventado', 0), (True, token, 99), (True, '', 0)]:
            with self.assertRaises(ValidationError):
                approve_reposo(actor=self.doctor, reposo_id=record.pk, expected_revision=revision, review_token=review, confirmed=confirmed)
        record.refresh_from_db()
        self.assertEqual(record.estado, 'borrador')

    def test_expired_review_is_rejected(self):
        record = self.draft()
        _, _, _, token = review_reposo(actor=self.doctor, reposo_id=record.pk)
        with patch('django.core.signing.time.time', return_value=time.time()+1900):
            with self.assertRaisesMessage(ValidationError, 'caducó'):
                approve_reposo(actor=self.doctor, reposo_id=record.pk, expected_revision=0, review_token=token, confirmed=True)

    def test_clinical_correction_invalidates_previously_reviewed_data(self):
        record = self.draft()
        _, _, _, token = review_reposo(actor=self.doctor, reposo_id=record.pk)
        correct_history(actor=self.doctor, history_id=self.history.pk, data={'diagnostico': 'Corregido'}, reason='Ficticio', expected_version=0)
        with self.assertRaisesMessage(ValidationError, 'datos cambiaron'):
            approve_reposo(actor=self.doctor, reposo_id=record.pk, expected_revision=0, review_token=token, confirmed=True)
        self.assertEqual(self.approve(record).estado, 'emitida')

    def test_patient_or_doctor_printed_data_changes_require_new_review(self):
        record = self.draft()
        _, _, _, token = review_reposo(actor=self.doctor, reposo_id=record.pk)
        update_patient(actor=self.nurse, patient_id=self.patient.pk, data={'tipo_paciente': 'estudiante', 'nombre': 'Nombre revisado'})
        with self.assertRaisesMessage(ValidationError, 'datos cambiaron'):
            approve_reposo(actor=self.doctor, reposo_id=record.pk, expected_revision=0, review_token=token, confirmed=True)
        _, _, _, token = review_reposo(actor=self.doctor, reposo_id=record.pk)
        self.doctor.nombre = 'Médico revisado'
        self.doctor.save(update_fields=['nombre'])
        with self.assertRaisesMessage(ValidationError, 'datos cambiaron'):
            approve_reposo(actor=self.doctor, reposo_id=record.pk, expected_revision=0, review_token=token, confirmed=True)

    def test_midnight_date_change_requires_new_review(self):
        record = self.draft()
        _, snapshot, _, token = review_reposo(actor=self.doctor, reposo_id=record.pk)
        tomorrow = date.fromisoformat(snapshot['fecha_emision'])+timedelta(days=1)
        with patch('Hisotria_clinica.reposos.timezone.localdate', return_value=tomorrow):
            with self.assertRaisesMessage(ValidationError, 'datos cambiaron'):
                approve_reposo(actor=self.doctor, reposo_id=record.pk, expected_revision=0, review_token=token, confirmed=True)

    def test_draft_update_requires_reason_audits_diff_and_invalidates_old_token(self):
        record = self.draft()
        _, _, _, token = review_reposo(actor=self.doctor, reposo_id=record.pk)
        with self.assertRaises(ValidationError):
            update_reposo_draft(actor=self.doctor, reposo_id=record.pk, data=self.data, expected_revision=0, reason='')
        record = update_reposo_draft(actor=self.doctor, reposo_id=record.pk, data={**self.data, 'dias': 4}, expected_revision=0, reason='Cambio ficticio')
        self.assertEqual(record.revision, 1)
        event = self.history.cambios_clinicos.first()
        self.assertEqual(event.anteriores['constancia_reposo']['dias'], 3)
        self.assertEqual(event.nuevos['constancia_reposo']['dias'], 4)
        with self.assertRaises(ValidationError):
            approve_reposo(actor=self.doctor, reposo_id=record.pk, expected_revision=1, review_token=token, confirmed=True)
        with self.assertRaises(ValidationError):
            update_reposo_draft(actor=self.doctor, reposo_id=record.pk, data=self.data, expected_revision=0, reason='Desactualizado')

    def test_only_responsible_authorized_doctor_can_prepare_update_preview_and_approve(self):
        record = self.draft()
        _, _, _, token = review_reposo(actor=self.doctor, reposo_id=record.pk)
        for user in [self.other_doctor, self.nurse, self.admin, account('reposo-pending@example.invalid', 'medico', 'pendiente')]:
            for action in [lambda: create_reposo_draft(actor=user, history_id=self.history.pk, data=self.data),
                           lambda: update_reposo_draft(actor=user, reposo_id=record.pk, data=self.data, expected_revision=0, reason='Ficticio'),
                           lambda: review_reposo(actor=user, reposo_id=record.pk),
                           lambda: approve_reposo(actor=user, reposo_id=record.pk, expected_revision=0, review_token=token, confirmed=True)]:
                with self.assertRaises(PermissionDenied):
                    action()
        record.refresh_from_db()
        self.assertEqual(record.estado, 'borrador')

    def test_role_revocation_is_checked_even_if_actor_object_is_stale(self):
        record = self.draft()
        _, _, _, token = review_reposo(actor=self.doctor, reposo_id=record.pk)
        type(self.doctor).objects.filter(pk=self.doctor.pk).update(approval_status='rechazado')
        with self.assertRaises(PermissionDenied):
            approve_reposo(actor=self.doctor, reposo_id=record.pk, expected_revision=0, review_token=token, confirmed=True)

    def test_saved_pdf_is_not_regenerated_after_patient_history_or_doctor_changes(self):
        issued = self.approve(self.draft())
        before = list(ConstanciaReposo.objects.filter(pk=issued.pk).values())
        original = bytes(issued.pdf)
        update_patient(actor=self.nurse, patient_id=self.patient.pk, data={'tipo_paciente': 'externo', 'nombre': 'Cambiado'})
        correct_history(actor=self.doctor, history_id=self.history.pk, data={'diagnostico': 'Nuevo'}, reason='Ficticio', expected_version=0)
        self.doctor.nombre = 'Otro nombre'
        self.doctor.save(update_fields=['nombre'])
        with patch('Hisotria_clinica.reposos.render_reposo', side_effect=AssertionError('No regenerar')):
            _, content = issued_reposo_pdf(actor=self.doctor, reposo_id=issued.pk)
        self.assertEqual(content, original)
        self.assertEqual(list(ConstanciaReposo.objects.filter(pk=issued.pk).values()), before)

    def test_emitted_model_queryset_sql_updates_and_deletes_are_blocked(self):
        record = self.approve(self.draft())
        record.motivo_reposo = 'No guardar'
        with self.assertRaises(ValidationError):
            record.save()
        with self.assertRaises(ValidationError):
            record.delete()
        with self.assertRaises(IntegrityError), transaction.atomic():
            ConstanciaReposo.objects.filter(pk=record.pk).update(pdf=b'otra cosa')
        with self.assertRaises(IntegrityError), transaction.atomic():
            ConstanciaReposo.objects.filter(pk=record.pk).delete()
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute('UPDATE "Hisotria_clinica_constanciareposo" SET pdf_sha256 = %s WHERE id = %s', ['f'*64, record.pk])
        with self.assertRaises(ValidationError):
            update_reposo_draft(actor=self.doctor, reposo_id=record.pk, data=self.data, expected_revision=record.revision, reason='No autorizado')
        record.refresh_from_db()
        self.assertEqual(record.motivo_reposo, self.data['motivo_reposo'])

    def test_new_version_keeps_original_pdf_and_links_previous_version(self):
        first = self.approve(self.draft())
        original = bytes(first.pdf)
        second = self.draft(previous_id=first.pk, correction_reason='Corrección de días ficticia')
        self.assertEqual(second.numero_version, 2)
        self.assertEqual(second.anterior_id, first.pk)
        second = update_reposo_draft(actor=self.doctor, reposo_id=second.pk, data={**self.data, 'dias': 5}, expected_revision=0, reason='Ajuste ficticio')
        second = self.approve(second)
        self.assertNotEqual(bytes(second.pdf), original)
        self.assertEqual(issued_reposo_pdf(actor=self.doctor, reposo_id=first.pk)[1], original)
        self.assertEqual(ConstanciaReposo.objects.filter(estado='emitida').count(), 2)
        self.assertEqual(second.datos_emitidos['anterior_id'], first.pk)
        self.assertEqual(second.aprobado_por, self.doctor)

    def test_duplicate_drafts_repeated_approvals_and_nonlatest_corrections_are_rejected(self):
        record = self.draft()
        with self.assertRaises(ValidationError):
            self.draft()
        first = self.approve(record)
        with self.assertRaises(ValidationError):
            self.draft()
        with self.assertRaises(ValidationError):
            self.draft(previous_id=first.pk)
        second = self.approve(self.draft(previous_id=first.pk, correction_reason='Ficticio'))
        with self.assertRaises(ValidationError):
            self.draft(previous_id=first.pk, correction_reason='Versión antigua')
        with self.assertRaises(ValidationError):
            approve_reposo(actor=self.doctor, reposo_id=second.pk, expected_revision=0, review_token='repetido', confirmed=True)

    def test_audit_failures_roll_back_creation_update_and_approval(self):
        with patch('Hisotria_clinica.reposos.AuditoriaClinica.objects.create', side_effect=RuntimeError('Synthetic')):
            with self.assertRaises(RuntimeError):
                self.draft()
        self.assertEqual(ConstanciaReposo.objects.count(), 0)
        record = self.draft()
        with patch('Hisotria_clinica.reposos.AuditoriaClinica.objects.create', side_effect=RuntimeError('Synthetic')):
            with self.assertRaises(RuntimeError):
                update_reposo_draft(actor=self.doctor, reposo_id=record.pk, data={**self.data, 'dias': 9}, expected_revision=0, reason='Ficticio')
            with self.assertRaises(RuntimeError):
                self.approve(record)
        record.refresh_from_db()
        self.assertEqual(record.dias, 3)
        self.assertEqual(record.revision, 0)
        self.assertEqual(record.estado, 'borrador')
        self.assertEqual(bytes(record.pdf), b'')
        self.assertIsNone(record.aprobado_en)

    def test_category_text_for_all_five_types_and_pnf_only_for_students(self):
        record = self.draft()
        expected = {'estudiante': 'estudiante:', 'profesor': 'profesor(a):',
                    'obrero_tecnico': 'personal obrero/técnico:', 'administrativo': 'personal administrativo:',
                    'externo': 'paciente externo:'}
        for category, label in expected.items():
            Estudiante.objects.filter(pk=self.patient.pk).update(tipo_paciente=category)
            _, snapshot, content, _ = review_reposo(actor=self.doctor, reposo_id=record.pk)
            self.assertIn(label, self.text(content))
            self.assertEqual(bool(snapshot['paciente']['pnf']), category == 'estudiante')
            self.assertEqual('PNF ficticio' in self.text(content), category == 'estudiante')

    def test_unverified_missing_identity_or_incomplete_source_blocks_preparation(self):
        for field, value in [('tipo_paciente', None), ('cedula', '')]:
            old = getattr(self.patient, field)
            Estudiante.objects.filter(pk=self.patient.pk).update(**{field: value})
            with self.assertRaises(ValidationError):
                self.draft()
            Estudiante.objects.filter(pk=self.patient.pk).update(**{field: old})
        type(self.history).objects.filter(pk=self.history.pk).update(diagnostico='')
        with self.assertRaises(ValidationError):
            self.draft()

    def test_pnf_is_not_required_and_is_not_inferred_from_worker_job(self):
        Estudiante.objects.filter(pk=self.patient.pk).update(tipo_paciente='externo', pnf='', cargo_laboral='No es dependencia')
        _, snapshot, content, _ = review_reposo(actor=self.doctor, reposo_id=self.draft().pk)
        self.assertEqual(snapshot['paciente']['pnf'], '')
        self.assertNotIn('No es dependencia', self.text(content))

    def test_oversized_pdf_content_blocks_review_and_approval_without_changing_draft(self):
        self.data['motivo_reposo'] = 'Texto muy largo. '*400
        record = self.draft()
        with self.assertRaisesMessage(ValidationError, 'No se ha recortado'):
            review_reposo(actor=self.doctor, reposo_id=record.pk)
        self.assertEqual(self.client.get(reverse('detalle_reposo', args=[record.pk])).status_code, 422)
        record.refresh_from_db()
        self.assertEqual(record.estado, 'borrador')
        self.assertEqual(bytes(record.pdf), b'')

    def test_literal_text_is_escaped_in_pdf_and_html(self):
        self.data['motivo_reposo'] = '<script>ficticio</script> & áéñ'
        record = self.draft()
        _, _, content, _ = review_reposo(actor=self.doctor, reposo_id=record.pk)
        self.assertIn(self.data['motivo_reposo'], self.text(content))
        response = self.client.get(reverse('detalle_reposo', args=[record.pk]))
        self.assertContains(response, '&lt;script&gt;ficticio&lt;/script&gt;')
        self.assertNotContains(response, '<script>ficticio</script>')

    def test_corrupted_draft_period_or_chain_is_not_approved(self):
        record = self.draft()
        ConstanciaReposo.objects.filter(pk=record.pk).update(fecha_fin=date(2026, 2, 1))
        with self.assertRaisesMessage(ValidationError, 'período'):
            review_reposo(actor=self.doctor, reposo_id=record.pk)
        ConstanciaReposo.objects.filter(pk=record.pk).update(fecha_fin=date(2026, 1, 17), numero_version=3)
        with self.assertRaisesMessage(ValidationError, 'primera versión'):
            review_reposo(actor=self.doctor, reposo_id=record.pk)

    def test_download_validates_saved_hash_without_falling_back_to_regeneration(self):
        record = self.approve(self.draft())
        record.pdf = b'contenido alterado en memoria'
        with patch('Hisotria_clinica.reposos.ConstanciaReposo.objects.get', return_value=record):
            with self.assertRaisesMessage(ValidationError, 'integridad'):
                issued_reposo_pdf(actor=self.doctor, reposo_id=record.pk)

    def test_http_prepare_review_approve_download_and_print_workflow(self):
        response = self.client.post(reverse('nuevo_reposo', args=[self.history.pk]), self.data)
        self.assertEqual(response.status_code, 302)
        record = ConstanciaReposo.objects.get()
        response = self.client.get(reverse('detalle_reposo', args=[record.pk]))
        self.assertContains(response, 'Aprobar y guardar PDF definitivo')
        form = response.context['approval_form']
        preview = self.client.get(reverse('preview_reposo', args=[record.pk]))
        self.assertEqual(preview['Content-Type'], 'application/pdf')
        self.assertIn('BORRADOR', self.text(preview.content))
        result = self.client.post(reverse('aprobar_reposo', args=[record.pk]),
            {**form.initial, 'confirmacion': 'on'})
        self.assertEqual(result.status_code, 302)
        issued = self.client.get(reverse('reposo_pdf', args=[record.pk]))
        self.assertEqual(issued.status_code, 200)
        self.assertIn('no-store', issued['Cache-Control'])
        self.assertEqual(issued['X-Frame-Options'], 'SAMEORIGIN')
        self.assertTrue(issued['Content-Disposition'].startswith('inline'))
        self.assertTrue(self.client.get(reverse('reposo_pdf', args=[record.pk]), {'download': '1'})['Content-Disposition'].startswith('attachment'))
        self.assertEqual(self.client.get(reverse('imprimir_reposo', args=[record.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('aprobar_reposo', args=[record.pk])).status_code, 405)
        self.assertEqual(self.client.post(reverse('reposo_pdf', args=[record.pk]), {}).status_code, 405)

    def test_http_edit_and_missing_confirmation_do_not_emit(self):
        record = self.draft()
        self.assertEqual(self.client.post(reverse('aprobar_reposo', args=[record.pk]), {}).status_code, 422)
        self.assertEqual(self.client.post(reverse('editar_reposo', args=[record.pk]),
            {**self.data, 'dias': 4, 'motivo_cambio': 'Cambio ficticio', 'expected_revision': 0}).status_code, 302)
        record.refresh_from_db()
        self.assertEqual(record.dias, 4)
        self.assertEqual(record.estado, 'borrador')

    def test_http_nurse_admin_and_nonresponsible_doctor_cannot_approve_or_access_drafts(self):
        record = self.draft()
        for user in [self.nurse, self.admin, self.other_doctor]:
            login_as(self.client, user)
            self.assertEqual(self.client.get(reverse('nuevo_reposo', args=[self.history.pk])).status_code, 403)
            self.assertEqual(self.client.get(reverse('detalle_reposo', args=[record.pk])).status_code, 403)
            self.assertEqual(self.client.get(reverse('preview_reposo', args=[record.pk])).status_code, 403)
            self.assertEqual(self.client.post(reverse('aprobar_reposo', args=[record.pk]), {}).status_code, 403)
            self.assertNotContains(self.client.get(reverse('detalle_historia', args=[self.history.pk])), reverse('detalle_reposo', args=[record.pk]))

    def test_other_doctors_can_read_issued_versions_but_nurse_admin_cannot_download(self):
        record = self.approve(self.draft())
        login_as(self.client, self.other_doctor)
        self.assertEqual(self.client.get(reverse('reposo_pdf', args=[record.pk])).status_code, 200)
        self.assertEqual(list(reposos_for(self.other_doctor, self.history.pk)), [record])
        for user in [self.nurse, self.admin]:
            login_as(self.client, user)
            self.assertEqual(self.client.get(reverse('reposo_pdf', args=[record.pk])).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('reposo_pdf', args=[record.pk])).status_code, 302)

    def test_create_update_and_approval_require_csrf(self):
        record = self.draft()
        client = Client(enforce_csrf_checks=True)
        login_as(client, self.doctor)
        for route, pk in [('nuevo_reposo', self.history.pk), ('editar_reposo', record.pk), ('aprobar_reposo', record.pk)]:
            self.assertEqual(client.post(reverse(route, args=[pk]), self.data).status_code, 403)

    def test_unknown_ids_and_invalid_previous_parameters_return_404(self):
        for route in ['detalle_reposo', 'preview_reposo', 'reposo_pdf', 'imprimir_reposo']:
            self.assertEqual(self.client.get(reverse(route, args=[999999])).status_code, 404)
        self.assertEqual(self.client.get(reverse('nuevo_reposo', args=[self.history.pk]), {'anterior': 'invalid'}).status_code, 404)

    def test_duplicate_correction_form_shows_validation_error_instead_of_server_error(self):
        first = self.approve(self.draft())
        self.draft(previous_id=first.pk, correction_reason='Primera corrección ficticia')
        url = reverse('nuevo_reposo', args=[self.history.pk])+f'?anterior={first.pk}'
        response = self.client.post(url, {**self.data, 'motivo_correccion': 'Solicitud repetida'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ya existe un borrador')
        self.assertEqual(ConstanciaReposo.objects.filter(estado='borrador').count(), 1)

    def test_five_lines_fit_and_a_sixth_line_blocks_preview(self):
        self.data['motivo_reposo'] = '\n'.join(f'Línea ficticia {index}' for index in range(1, 6))
        record = self.draft()
        _, _, content, _ = review_reposo(actor=self.doctor, reposo_id=record.pk)
        for index in range(1, 6):
            self.assertIn(f'Línea ficticia {index}', self.text(content))
        record = update_reposo_draft(actor=self.doctor, reposo_id=record.pk,
            data={**self.data, 'motivo_reposo': self.data['motivo_reposo']+'\nSexta línea'}, expected_revision=0, reason='Ensayo ficticio')
        with self.assertRaisesMessage(ValidationError, 'No se ha recortado'):
            review_reposo(actor=self.doctor, reposo_id=record.pk)

    def test_reading_an_issued_version_is_read_only_even_when_patient_becomes_unverified(self):
        record = self.approve(self.draft())
        Estudiante.objects.filter(pk=self.patient.pk).update(tipo_paciente=None)
        with CaptureQueriesContext(connection) as queries:
            _, content = issued_reposo_pdf(actor=self.doctor, reposo_id=record.pk)
        self.assertEqual(content, bytes(record.pdf))
        self.assertFalse([q for q in queries if q['sql'].lstrip().upper().startswith(('INSERT ', 'UPDATE ', 'DELETE '))])

    def test_period_before_birth_and_nonstring_review_are_rejected(self):
        self.data['fecha_inicio'] = date(1999, 1, 1)
        record = self.draft()
        with self.assertRaisesMessage(ValidationError, 'nacimiento'):
            review_reposo(actor=self.doctor, reposo_id=record.pk)
        for token in [None, {}, 123]:
            with self.assertRaisesMessage(ValidationError, 'revisión'):
                approve_reposo(actor=self.doctor, reposo_id=record.pk, expected_revision=0, review_token=token, confirmed=True)
