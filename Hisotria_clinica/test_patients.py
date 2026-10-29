from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse

from LoginRegister.test_security import account, login_as
from .forms import EstudianteForm
from .models import AuditoriaPaciente, Estudiante, HistoriaClinica
from .services import register_patient, update_patient


def personal_data(**changes):
    data = dict(nombre='Paciente', apellido='Ficticio', cedula='V-100001', tipo_paciente='estudiante',
        edo_civil='Soltero', sexo='Masculino', direccion='Dirección ficticia',
        contacto_emergencia='Contacto ficticio', telefono='0000000000', fecha_nacimiento='2000-01-01')
    data.update(changes)
    return data


class PatientClassificationTests(TestCase):
    def setUp(self):
        self.nurse = account('nurse@example.invalid', 'enfermera')
        self.admin = account('admin@example.invalid', 'administrador')
        login_as(self.client, self.nurse)

    def test_all_five_types_register_without_optional_institutional_data(self):
        for index, category in enumerate(Estudiante.Tipo.values):
            with self.subTest(category=category):
                response = self.client.post(reverse('registro_paciente'), personal_data(cedula=f'V-{index+100}', tipo_paciente=category))
                self.assertEqual(response.status_code, 302)
                self.assertTrue(Estudiante.objects.filter(tipo_paciente=category).exists())
        self.assertEqual(Estudiante.objects.count(), 5)
        self.assertEqual(HistoriaClinica.objects.count(), 0)
        self.assertEqual(AuditoriaPaciente.objects.count(), 5)

    def test_former_members_and_never_affiliated_people_use_the_same_external_type(self):
        for index, description in enumerate(['Exestudiante', 'Exprofesor', 'Extrajador', 'Nunca afiliado']):
            patient = register_patient(actor=self.nurse, data=personal_data(cedula=f'E-{index+500}', apellido=description, tipo_paciente='externo'))
            self.assertEqual(patient.tipo_paciente, 'externo')
            self.assertEqual(patient.pnf, '')
            self.assertEqual(patient.cargo_laboral, '')
        self.assertEqual(len(Estudiante.Tipo.choices), 5)

    def test_required_identity_and_type_are_enforced_in_form_and_service(self):
        for changes in [{'cedula': ''}, {'cedula': '????'}, {'cedula': 'SIN-DIGITOS'}, {'tipo_paciente': ''}, {'tipo_paciente': 'desvinculado'}]:
            self.assertFalse(EstudianteForm(data=personal_data(**changes)).is_valid())
            with self.assertRaises(ValidationError):
                register_patient(actor=self.nurse, data=personal_data(**changes))

    def test_student_pnf_and_worker_job_are_optional_and_category_specific(self):
        student = register_patient(actor=self.nurse, data=personal_data(pnf='PNF ficticio'))
        worker = register_patient(actor=self.nurse, data=personal_data(cedula='V-200', tipo_paciente='obrero_tecnico', cargo_laboral='Técnico ficticio'))
        self.assertEqual(student.pnf, 'PNF ficticio')
        self.assertEqual(worker.cargo_laboral, 'Técnico ficticio')
        with self.assertRaises(ValidationError):
            register_patient(actor=self.nurse, data=personal_data(cedula='V-300', tipo_paciente='externo', pnf='No aplicable'))
        form = EstudianteForm(data=personal_data(cedula='V-301', tipo_paciente='externo', pnf='Inyectado', cargo_laboral='Inyectado'))
        self.assertTrue(form.is_valid(), form.errors)
        external = register_patient(actor=self.nurse, data=form.cleaned_data)
        self.assertEqual((external.pnf, external.cargo_laboral), ('', ''))

    def test_duplicates_include_case_and_surrounding_spaces_without_rewriting_legacy_id(self):
        old = Estudiante.objects.create(**personal_data(cedula=' v-100001 '), edad=77)
        with self.assertRaises(ValidationError):
            register_patient(actor=self.nurse, data=personal_data(cedula='V-100001'))
        old.refresh_from_db()
        self.assertEqual(old.cedula, ' v-100001 ')
        self.assertEqual(old.edad, 77)

    def test_category_change_keeps_identity_history_and_previous_institutional_values(self):
        patient = register_patient(actor=self.nurse, data=personal_data(pnf='PNF anterior'))
        history = HistoriaClinica.objects.create(estudiante=patient, fecha_consulta='2026-10-27', motivo_consulta='Ficticio', diagnostico='Ficticio', tratamiento='Ficticio')
        before = list(HistoriaClinica.objects.values())
        updated = update_patient(actor=self.nurse, patient_id=patient.pk, data={'tipo_paciente': 'externo'})
        self.assertEqual(updated.pk, patient.pk)
        self.assertEqual(updated.pnf, 'PNF anterior')
        self.assertEqual(updated.cedula, patient.cedula)
        self.assertEqual(list(HistoriaClinica.objects.values()), before)
        self.assertEqual(history.estudiante_id, updated.pk)
        event = AuditoriaPaciente.objects.get(accion='modificacion')
        self.assertEqual(event.usuario, self.nurse)
        self.assertEqual(event.anteriores, {'tipo_paciente': 'estudiante'})
        self.assertEqual(event.nuevos, {'tipo_paciente': 'externo'})

    def test_equivalent_separators_are_duplicate_without_rewriting_identifiers(self):
        patient = register_patient(actor=self.nurse, data=personal_data(cedula='V-100001'))
        with self.assertRaises(ValidationError):
            register_patient(actor=self.nurse, data=personal_data(cedula='V.100001'))
        self.assertEqual(patient.cedula, 'V-100001')
        self.assertEqual(patient.cedula_clave, 'V100001')
        response = self.client.get(reverse('lista_pacientes'), {'q': 'v.100001'})
        self.assertEqual(list(response.context['patients']), [patient])
        legacy = Estudiante.objects.create(**personal_data(cedula=' e . 900 '), edad=77)
        with self.assertRaises(ValidationError):
            register_patient(actor=self.nurse, data=personal_data(cedula='E-900'))
        legacy.refresh_from_db()
        self.assertEqual(legacy.cedula, ' e . 900 ')
        self.assertIsNone(legacy.cedula_clave)

    def test_legacy_patient_can_be_classified_without_changing_stored_age_or_identity(self):
        patient = Estudiante.objects.create(**personal_data(tipo_paciente=None), edad=77)
        self.assertEqual(patient.categoria_visible, 'Por verificar')
        updated = update_patient(actor=self.nurse, patient_id=patient.pk, data={'tipo_paciente': 'profesor'})
        self.assertEqual(updated.edad, 77)
        self.assertEqual(updated.cedula, patient.cedula)

    def test_admin_is_read_only_for_personal_data(self):
        patient = register_patient(actor=self.nurse, data=personal_data())
        login_as(self.client, self.admin)
        self.assertEqual(self.client.get(reverse('detalle_paciente', args=[patient.pk])).status_code, 200)
        self.assertEqual(self.client.post(reverse('editar_paciente', args=[patient.pk]), personal_data(tipo_paciente='externo')).status_code, 403)
        with self.assertRaises(PermissionDenied):
            update_patient(actor=self.admin, patient_id=patient.pk, data={'tipo_paciente': 'externo'})

    def test_filters_by_category_and_unverified_indicator(self):
        register_patient(actor=self.nurse, data=personal_data())
        external = register_patient(actor=self.nurse, data=personal_data(cedula='E-200', tipo_paciente='externo'))
        Estudiante.objects.create(**personal_data(cedula='V-300', tipo_paciente=None), edad=77)
        response = self.client.get(reverse('lista_pacientes'), {'tipo': 'externo'})
        self.assertEqual(list(response.context['patients']), [external])
        self.assertEqual(self.client.get(reverse('lista_pacientes'), {'tipo': 'por_verificar'}).context['patients'].count(), 1)

    def test_update_via_form_preserves_hidden_old_pnf_and_audits_changes(self):
        patient = register_patient(actor=self.nurse, data=personal_data(pnf='PNF anterior'))
        response = self.client.post(reverse('editar_paciente', args=[patient.pk]), personal_data(tipo_paciente='externo'))
        self.assertEqual(response.status_code, 302)
        patient.refresh_from_db()
        self.assertEqual(patient.pnf, 'PNF anterior')
        self.assertEqual(patient.tipo_paciente, 'externo')

    def test_patient_audit_failure_rolls_back_changes(self):
        patient = register_patient(actor=self.nurse, data=personal_data())
        with patch('Hisotria_clinica.services.AuditoriaPaciente.objects.create', side_effect=RuntimeError('Synthetic')):
            with self.assertRaises(RuntimeError):
                update_patient(actor=self.nurse, patient_id=patient.pk, data={'tipo_paciente': 'externo'})
        patient.refresh_from_db()
        self.assertEqual(patient.tipo_paciente, 'estudiante')
