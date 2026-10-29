from datetime import date, datetime, timedelta, timezone as datetime_timezone

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from LoginRegister.test_security import account, login_as
from .forms import LlegadaForm
from .models import Atencion, CambioEstadoAtencion, Estudiante, HistoriaClinica
from .reports import daily_report, pending_report
from .services import correct_history, create_history, register_arrival, register_patient, transition_attention
from .test_patients import personal_data


class ReportTests(TestCase):
    def setUp(self):
        self.nurse = account('report-nurse@example.invalid', 'enfermera')
        self.other_nurse = account('report-nurse2@example.invalid', 'enfermera')
        self.doctor = account('report-doctor@example.invalid', 'medico')
        self.other_doctor = account('report-doctor2@example.invalid', 'medico')
        self.admin = account('report-admin@example.invalid', 'administrador', is_staff=True, is_superuser=True)
        self.patient = register_patient(actor=self.nurse, data=personal_data())
        self.clinical = dict(fecha_consulta=date(2026, 1, 5), motivo_consulta='Consulta ficticia',
            diagnostico='Diagnóstico ficticio', tratamiento='Tratamiento ficticio', observaciones='')
        login_as(self.client, self.nurse)

    def arrive(self, patient=None, **kwargs):
        return register_arrival(actor=self.nurse, patient_id=(patient or self.patient).pk,
            arrival=timezone.now()-timedelta(days=2), reason='Visita ficticia', **kwargs)

    def complete(self, *, patient=None, doctor=None, nurse_id=None, shift='', finished=None):
        attention = self.arrive(patient, nurse_id=nurse_id, shift=shift)
        attention = transition_attention(actor=self.nurse, attention_id=attention.pk, target='en_atencion', expected_version=0)
        history = create_history(actor=doctor or self.doctor, patient_id=attention.paciente_id,
            attention_id=attention.pk, data=self.clinical)
        finished = finished or datetime(2026, 1, 15, 12, tzinfo=datetime_timezone.utc)
        Atencion.objects.filter(pk=attention.pk).update(actualizada_en=finished)
        attention.refresh_from_db()
        return attention, history

    def report(self, start=date(2026, 1, 15), end=date(2026, 1, 15)):
        return daily_report(actor=self.nurse, start=start, end=end)

    def test_daily_counts_only_completed_complete_traceable_consultations(self):
        attention, _ = self.complete()
        pending = self.arrive()
        report = self.report()
        self.assertEqual(report.count, 1)
        self.assertEqual(report.days[0].teams[0].rows[0]['attention'], attention)
        self.assertEqual(pending_report(actor=self.nurse).rows, [pending])
        transition_attention(actor=self.nurse, attention_id=pending.pk, target='en_atencion', expected_version=0)
        self.assertEqual(pending_report(actor=self.nurse).count, 0)
        transition_attention(actor=self.nurse, attention_id=pending.pk, target='cancelado', expected_version=1)
        self.assertEqual(self.report().count, 1)

    @override_settings(TIME_ZONE='UTC')
    def test_completion_date_is_explicitly_caracas_and_range_is_inclusive(self):
        before_midnight = datetime(2026, 1, 16, 3, 59, tzinfo=datetime_timezone.utc)
        at_midnight = datetime(2026, 1, 16, 4, 0, tzinfo=datetime_timezone.utc)
        self.complete(finished=before_midnight)
        self.complete(finished=at_midnight)
        self.assertEqual(self.report().count, 1)
        report = self.report(date(2026, 1, 15), date(2026, 1, 16))
        self.assertEqual([day.count for day in report.days], [1, 1])
        self.assertEqual(report.days[0].teams[0].rows[0]['completed_at'].hour, 23)
        self.assertEqual(self.report(date(2026, 1, 16), date(2026, 1, 16)).count, 1)

    def test_empty_dates_have_their_own_section(self):
        self.complete()
        report = self.report(date(2026, 1, 14), date(2026, 1, 16))
        self.assertEqual([day.date for day in report.days], [date(2026, 1, 14), date(2026, 1, 15), date(2026, 1, 16)])
        self.assertEqual([day.count for day in report.days], [0, 1, 0])

    def test_leap_day_and_maximum_inclusive_period(self):
        report = self.report(date(2024, 2, 28), date(2024, 3, 1))
        self.assertEqual([day.date for day in report.days], [date(2024, 2, 28), date(2024, 2, 29), date(2024, 3, 1)])
        self.assertEqual(len(self.report(date(2024, 1, 1), date(2024, 12, 31)).days), 366)
        with self.assertRaises(ValidationError):
            self.report(date(2024, 1, 1), date(2025, 1, 1))

    def test_teams_are_separated_by_recorded_doctor_nurse_and_shift(self):
        self.complete(nurse_id=self.nurse.pk, shift='Mañana')
        self.complete(nurse_id=self.other_nurse.pk, shift='Mañana')
        self.complete(nurse_id=self.nurse.pk, shift='Tarde')
        self.complete(doctor=self.other_doctor, nurse_id=self.nurse.pk, shift='Mañana')
        report = self.report()
        self.assertEqual(report.count, 4)
        self.assertEqual(len(report.days[0].teams), 4)
        self.assertTrue(all(len(team.rows) == 1 for team in report.days[0].teams))

    def test_nurse_and_shift_are_not_inferred_from_arrival_user(self):
        self.complete()
        team = self.report().days[0].teams[0]
        self.assertIsNone(team.nurse)
        self.assertEqual(team.shift, '')

    def test_duplicate_trace_events_do_not_duplicate_attention_and_repeat_visits_are_kept(self):
        attention, _ = self.complete()
        CambioEstadoAtencion.objects.create(atencion=attention, usuario=self.doctor, anterior='en_atencion', nuevo='atendido')
        self.assertEqual(self.report().count, 1)
        self.complete()
        self.assertEqual(self.report().count, 2)

    def test_age_is_calculated_at_completion_date_not_today_or_stored_age(self):
        self.patient.fecha_nacimiento = date(2000, 1, 16)
        self.patient.edad = 99
        self.patient.save(update_fields=['fecha_nacimiento', 'edad'])
        self.complete()
        self.assertEqual(self.report().days[0].teams[0].rows[0]['age'], 25)
        self.patient.refresh_from_db()
        self.assertEqual(self.patient.edad, 99)

    def test_invalid_historical_birth_date_does_not_produce_negative_age(self):
        self.complete()
        # Simulate a preexisting corrupt birth date after a valid visit was saved;
        # new consultations now reject such inconsistent source dates.
        self.patient.fecha_nacimiento = date(2030, 1, 1)
        self.patient.save(update_fields=['fecha_nacimiento'])
        self.assertIsNone(self.report().days[0].teams[0].rows[0]['age'])

    def test_correction_keeps_completion_date_and_report_uses_audited_current_diagnosis(self):
        attention, history = self.complete()
        correct_history(actor=self.doctor, history_id=history.pk, data={'diagnostico': 'Corrección ficticia'},
            reason='Justificación ficticia', expected_version=0)
        report = self.report()
        self.assertEqual(report.count, 1)
        self.assertEqual(report.days[0].teams[0].rows[0]['history'].diagnostico, 'Corrección ficticia')
        attention.refresh_from_db()
        self.assertEqual(attention.actualizada_en, datetime(2026, 1, 15, 12, tzinfo=datetime_timezone.utc))

    def test_historical_consultations_remain_visible_but_not_certified_as_completed(self):
        history = HistoriaClinica.objects.create(estudiante=self.patient, **{**self.clinical, 'fecha_consulta': date(2026, 1, 15)})
        report = self.report()
        self.assertEqual(report.count, 0)
        self.assertEqual(report.legacy_count, 1)
        self.assertEqual(report.legacy_samples, [history])
        history.refresh_from_db()
        self.assertIsNone(history.atencion_id)
        self.assertIsNone(history.medico_id)

    def test_inconsistent_closures_are_excluded_with_a_visible_reason(self):
        attention, history = self.complete()
        HistoriaClinica.objects.filter(pk=history.pk).update(medico=None)
        report = self.report()
        self.assertEqual(report.count, 0)
        self.assertEqual(report.excluded_count, 1)
        self.assertIn('médico responsable', report.excluded_samples[0]['reason'])
        # A record with no clinical relation is also not counted.
        other = self.arrive()
        Atencion.objects.filter(pk=other.pk).update(estado='atendido', actualizada_en=attention.actualizada_en)
        self.assertEqual(self.report().excluded_count, 2)

    def test_missing_completion_trace_does_not_certify_a_record(self):
        attention, _ = self.complete()
        # Keep all records: change the synthetic trace rather than delete it.
        attention.cambios_estado.filter(nuevo='atendido').update(nuevo='en_atencion')
        report = self.report()
        self.assertEqual(report.count, 0)
        self.assertIn('trazabilidad', report.excluded_samples[0]['reason'])

    def test_mismatched_patient_or_incomplete_diagnosis_is_not_reported_as_valid(self):
        attention, history = self.complete()
        other = register_patient(actor=self.nurse, data=personal_data(cedula='E-9999'))
        HistoriaClinica.objects.filter(pk=history.pk).update(estudiante=other)
        self.assertIn('no coincide', self.report().excluded_samples[0]['reason'])
        HistoriaClinica.objects.filter(pk=history.pk).update(estudiante=self.patient, diagnostico=' ')
        self.assertIn('incompleta', self.report().excluded_samples[0]['reason'])

    def test_inactive_historical_doctor_does_not_remove_valid_completed_consultations(self):
        self.complete()
        self.doctor.is_active = False
        self.doctor.save(update_fields=['is_active'])
        self.assertEqual(self.report().count, 1)

    def test_pending_default_includes_old_arrivals_and_only_current_pending_state(self):
        attention = self.arrive()
        self.assertEqual(pending_report(actor=self.nurse).rows, [attention])
        transition_attention(actor=self.nurse, attention_id=attention.pk, target='en_atencion', expected_version=0)
        self.assertEqual(pending_report(actor=self.nurse).count, 0)

    @override_settings(TIME_ZONE='UTC')
    def test_pending_date_range_uses_caracas_arrival_date(self):
        attention = self.arrive()
        Atencion.objects.filter(pk=attention.pk).update(fecha_hora_llegada=datetime(2026, 1, 16, 3, 59, tzinfo=datetime_timezone.utc))
        self.assertEqual(pending_report(actor=self.nurse, start=date(2026, 1, 15), end=date(2026, 1, 15)).count, 1)
        self.assertEqual(pending_report(actor=self.nurse, start=date(2026, 1, 16), end=date(2026, 1, 16)).count, 0)

    def test_all_categories_and_unverified_patients_are_supported(self):
        for index, category in enumerate(Estudiante.Tipo.values):
            patient = register_patient(actor=self.nurse, data=personal_data(cedula=f'R-{100+index}', tipo_paciente=category))
            self.complete(patient=patient)
        legacy = Estudiante.objects.create(**personal_data(cedula='OLD-900', tipo_paciente=None), edad=77)
        self.complete(patient=legacy)
        self.assertEqual(self.report().count, 6)
        self.assertIsNone(Estudiante.objects.get(pk=legacy.pk).tipo_paciente)

    def test_reports_do_not_write_to_patients_histories_accounts_or_audits(self):
        self.complete()
        self.arrive()
        with CaptureQueriesContext(connection) as queries:
            self.report()
            pending_report(actor=self.nurse)
        writes = [query['sql'] for query in queries if query['sql'].lstrip().upper().startswith(('INSERT ', 'UPDATE ', 'DELETE ', 'ALTER ', 'CREATE '))]
        self.assertEqual(writes, [])

    def test_admin_superuser_and_unapproved_accounts_cannot_access_reports(self):
        for user in [self.admin, account('pending-report@example.invalid', 'medico', 'pendiente')]:
            login_as(self.client, user)
            for route in ['registro_diario', 'reporte_pendientes']:
                self.assertEqual(self.client.get(reverse(route)).status_code, 403)
            with self.assertRaises(PermissionDenied):
                daily_report(actor=user, start=date(2026, 1, 15), end=date(2026, 1, 15))
            with self.assertRaises(PermissionDenied):
                pending_report(actor=user)

    def test_doctor_and_nurse_can_view_private_reports_and_post_cannot_modify_them(self):
        for user in [self.nurse, self.doctor]:
            login_as(self.client, user)
            for route in ['registro_diario', 'reporte_pendientes']:
                response = self.client.get(reverse(route))
                self.assertEqual(response.status_code, 200)
                self.assertIn('no-store', response.headers['Cache-Control'])
                self.assertEqual(self.client.post(reverse(route), {}).status_code, 405)

    def test_anonymous_and_deactivated_sessions_cannot_view_reports(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse('registro_diario')).status_code, 302)
        login_as(self.client, self.nurse)
        self.nurse.is_active = False
        self.nurse.save(update_fields=['is_active'])
        self.assertEqual(self.client.get(reverse('reporte_pendientes')).status_code, 302)

    def test_date_and_range_forms_reject_ambiguous_missing_or_excessive_periods(self):
        for data in [{'fecha': 'invalid'}, {'desde': '2026-01-01'}, {'hasta': '2026-01-01'},
                     {'desde': '2026-01-02', 'hasta': '2026-01-01'},
                     {'fecha': '2026-01-01', 'desde': '2026-01-01', 'hasta': '2026-01-02'},
                     {'desde': '2024-01-01', 'hasta': '2026-01-01'}]:
            for route in ['registro_diario', 'reporte_pendientes']:
                response = self.client.get(reverse(route), data)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['form'].errors)
                self.assertIsNone(response.context['report'])
        with self.assertRaises(ValidationError):
            self.report(date(2026, 1, 16), date(2026, 1, 15))
        with self.assertRaises(ValidationError):
            daily_report(actor=self.nurse, start=None, end=None)

    def test_single_date_and_range_render_correct_totals_and_long_escaped_text(self):
        self.clinical['diagnostico'] = '<script>ficticio</script> ' + ('Diagnóstico extenso con acentos. ' * 100)
        self.complete()
        response = self.client.get(reverse('registro_diario'), {'fecha': '2026-01-15'})
        self.assertEqual(response.context['report'].count, 1)
        self.assertContains(response, '&lt;script&gt;ficticio&lt;/script&gt;')
        self.assertNotContains(response, '<script>ficticio</script>')
        self.assertContains(response, 'Diagnóstico extenso con acentos.', count=100)
        response = self.client.get(reverse('registro_diario'), {'desde': '2026-01-14', 'hasta': '2026-01-16'})
        self.assertEqual(len(response.context['report'].days), 3)
        self.assertContains(response, 'No hay atenciones finalizadas verificables', count=2)

    def test_arrival_team_capture_is_optional_explicit_and_validated_server_side(self):
        attention = self.arrive(nurse_id=self.other_nurse.pk, shift='  Tarde  ')
        self.assertEqual(attention.enfermera_responsable, self.other_nurse)
        self.assertEqual(attention.turno, 'Tarde')
        transition_attention(actor=self.nurse, attention_id=attention.pk, target='cancelado', expected_version=0)
        for invalid in [self.doctor.pk, self.admin.pk]:
            with self.assertRaises(ValidationError):
                self.arrive(nurse_id=invalid)
        self.other_nurse.is_active = False
        self.other_nurse.save(update_fields=['is_active'])
        with self.assertRaises(ValidationError):
            self.arrive(nurse_id=self.other_nurse.pk)
        form = LlegadaForm(data={'arrival': timezone.localtime().strftime('%Y-%m-%dT%H:%M'), 'reason': 'Ficticio', 'nurse': self.doctor.pk})
        self.assertFalse(form.is_valid())

    def test_pending_screen_has_no_diagnosis_and_navigation_respects_report_roles(self):
        self.arrive()
        response = self.client.get(reverse('reporte_pendientes'))
        self.assertEqual(response.context['report'].count, 1)
        self.assertNotContains(response, '<th scope="col">Diagnóstico</th>', html=True)
        self.assertContains(self.client.get(reverse('dashboard')), reverse('registro_diario'))
        login_as(self.client, self.admin)
        self.assertNotContains(self.client.get(reverse('dashboard')), reverse('registro_diario'))
