from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class PatientUpgradePreservationTests(TransactionTestCase):
    def test_replacement_guards_preserve_preexisting_emitted_pdf_and_audit(self):
        # All schema reversal below is fixture cleanup on the independent test DB.
        self.assertIn('memory', str(connection.settings_dict['NAME']))
        executor = MigrationExecutor(connection)
        executor.migrate([('Hisotria_clinica', '0009_rest_certificates')])
        old = executor.loader.project_state([('Hisotria_clinica', '0009_rest_certificates')]).apps
        Patient = old.get_model('Hisotria_clinica', 'Estudiante')
        History = old.get_model('Hisotria_clinica', 'HistoriaClinica')
        Certificate = old.get_model('Hisotria_clinica', 'ConstanciaReposo')
        Audit = old.get_model('Hisotria_clinica', 'AuditoriaClinica')
        from LoginRegister.test_security import account
        from LoginRegister.models import Usuario
        from django.utils import timezone
        import hashlib
        actor = account('migration-replace@example.invalid', 'medico')
        patient = Patient.objects.create(nombre='Persona', apellido='Ficticia', cedula='OLD-REPLACE-1', edad=77,
            edo_civil='Soltero', sexo='Masculino', direccion='Ficticia', contacto_emergencia='Ficticio',
            telefono='0000', fecha_nacimiento='2000-01-01')
        history = History.objects.create(estudiante=patient, medico_id=actor.pk, fecha_consulta='2026-01-15',
            motivo_consulta='Ficticio', diagnostico='Ficticio', tratamiento='Ficticio')
        content = b'%PDF-fixture-sintetico-no-documento-real'
        certificate = Certificate.objects.create(historia=history, numero_version=1, estado='emitida',
            motivo_reposo='Ficticio', dias=2, fecha_inicio='2026-01-15', fecha_fin='2026-01-16',
            creado_por_id=actor.pk, aprobado_por_id=actor.pk, aprobado_en=timezone.now(),
            pdf=content, pdf_sha256=hashlib.sha256(content).hexdigest(), datos_emitidos={'schema': 1, 'formato': 'FOR-SSS-07'})
        Audit.objects.create(historia=history, usuario_id=actor.pk, motivo='Emisión ficticia',
                             nuevos={'constancia_reposo': {'id': certificate.pk, 'pdf_sha256': certificate.pdf_sha256}})
        source = [Patient, History, Certificate, Audit, Usuario]
        before = [list(model.objects.order_by('pk').values()) for model in source]
        try:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
            from .models import Estudiante, HistoriaClinica, ConstanciaReposo, AuditoriaClinica
            for model, rows in zip([Estudiante, HistoriaClinica, ConstanciaReposo, AuditoriaClinica, Usuario], before):
                self.assertEqual(list(model.objects.order_by('pk').values()), rows)
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'reposo_emitido_%'")
                self.assertEqual(len(cursor.fetchall()), 4)
                self.assertEqual(cursor.execute('PRAGMA foreign_key_check').fetchall(), [])
                self.assertEqual(cursor.execute('PRAGMA integrity_check').fetchall(), [('ok',)])
        finally:
            # Drop only the synthetic certificate table through a test-schema rollback;
            # an ordinary DELETE is correctly blocked for this emitted fixture.
            executor = MigrationExecutor(connection)
            executor.migrate([('Hisotria_clinica', '0008_clinical_history_document_fields')])
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())

    def test_reposo_migration_preserves_all_original_data_and_installs_immutability_guards(self):
        executor = MigrationExecutor(connection)
        executor.migrate([('Hisotria_clinica', '0008_clinical_history_document_fields')])
        old = executor.loader.project_state([('Hisotria_clinica', '0008_clinical_history_document_fields')]).apps
        Patient = old.get_model('Hisotria_clinica', 'Estudiante')
        History = old.get_model('Hisotria_clinica', 'HistoriaClinica')
        ClinicalAudit = old.get_model('Hisotria_clinica', 'AuditoriaClinica')
        from LoginRegister.test_security import account
        from LoginRegister.models import Usuario, AccountAudit
        doctor = account('rest-migration@example.invalid', 'medico')
        patient = Patient.objects.create(nombre='Persona', apellido='Ficticia', cedula='OLD-REST-1', edad=77,
            edo_civil='Soltero', sexo='Masculino', direccion='Ficticia', contacto_emergencia='Ficticio',
            telefono='0000', fecha_nacimiento='2000-01-01', lugar_nacimiento='Coro', telefono_emergencia='0001')
        history = History.objects.create(estudiante=patient, medico_id=doctor.pk, fecha_consulta='2026-01-15',
            motivo_consulta='Ficticio', diagnostico='Ficticio', tratamiento='Ficticio',
            enfermedad_actual='Ficticia', diagnostico_provisional='Ficticio', rp=True, lab=None, version=5)
        ClinicalAudit.objects.create(historia=history, usuario_id=doctor.pk, motivo='Ficticio', nuevos={'enfermedad_actual': 'Ficticia'})
        AccountAudit.objects.create(actor=doctor, target=doctor, action='synthetic_setup', reason='Ficticio')
        source = [Patient, History, ClinicalAudit, Usuario, AccountAudit]
        snapshots = [list(model.objects.order_by('pk').values()) for model in source]
        try:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
            from .models import ConstanciaReposo, Estudiante, HistoriaClinica, AuditoriaClinica
            for model, rows in zip([Estudiante, HistoriaClinica, AuditoriaClinica, Usuario, AccountAudit], snapshots):
                self.assertEqual(list(model.objects.order_by('pk').values()), rows)
            self.assertEqual(ConstanciaReposo.objects.count(), 0)
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name IN ('reposo_emitido_inmutable', 'reposo_emitido_no_borrar')")
                self.assertEqual({name for name, in cursor.fetchall()}, {'reposo_emitido_inmutable', 'reposo_emitido_no_borrar'})
                self.assertEqual(cursor.execute('PRAGMA foreign_key_check').fetchall(), [])
                self.assertEqual(cursor.execute('PRAGMA integrity_check').fetchall(), [('ok',)])
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())

    def test_history_pdf_fields_preserve_original_accounts_medical_relations_and_audits(self):
        executor = MigrationExecutor(connection)
        executor.migrate([('Hisotria_clinica', '0007_daily_register_options')])
        old = executor.loader.project_state([('Hisotria_clinica', '0007_daily_register_options')]).apps
        Patient = old.get_model('Hisotria_clinica', 'Estudiante')
        History = old.get_model('Hisotria_clinica', 'HistoriaClinica')
        Attention = old.get_model('Hisotria_clinica', 'Atencion')
        Audit = old.get_model('Hisotria_clinica', 'AuditoriaClinica')
        PatientAudit = old.get_model('Hisotria_clinica', 'AuditoriaPaciente')
        Event = old.get_model('Hisotria_clinica', 'CambioEstadoAtencion')
        from LoginRegister.test_security import account
        from LoginRegister.models import Usuario
        from django.utils import timezone
        doctor = account('history-pdf-migration@example.invalid', 'medico')
        patient = Patient.objects.create(nombre='Persona', apellido='Ficticia', cedula='OLD-HC-1', edad=77,
            edo_civil='Soltero', sexo='Masculino', direccion='Ficticia', contacto_emergencia='Familiar',
            telefono='0001', fecha_nacimiento='2000-01-01', tipo_paciente=None, pnf='PNF histórico')
        attention = Attention.objects.create(paciente=patient, fecha_hora_llegada=timezone.now(),
            motivo_visita='Ficticio', estado='atendido', registrada_por_id=doctor.pk, actualizada_por_id=doctor.pk)
        history = History.objects.create(estudiante=patient, atencion=attention, medico_id=doctor.pk,
            fecha_consulta='2026-01-15', motivo_consulta='Ficticio', diagnostico='No es diagnóstico provisional',
            tratamiento='Anterior', observaciones='No es enfermedad actual', version=3, rp=True, tto=False, lab=None)
        Audit.objects.create(historia=history, usuario_id=doctor.pk, motivo='Ficticio', nuevos={'diagnostico': history.diagnostico})
        PatientAudit.objects.create(paciente=patient, usuario_id=doctor.pk, accion='modificacion', nuevos={'telefono': '0001'})
        Event.objects.create(atencion=attention, usuario_id=doctor.pk, anterior='en_atencion', nuevo='atendido')
        source = [Patient, History, Attention, Audit, PatientAudit, Event, Usuario]
        snapshots = [list(model.objects.order_by('pk').values()) for model in source]
        try:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
            from .models import Estudiante, HistoriaClinica, Atencion, AuditoriaClinica, AuditoriaPaciente, CambioEstadoAtencion
            current = [Estudiante, HistoriaClinica, Atencion, AuditoriaClinica, AuditoriaPaciente, CambioEstadoAtencion, Usuario]
            for model, rows in zip(current, snapshots):
                self.assertEqual(list(model.objects.order_by('pk').values(*rows[0])), rows)
            upgraded = HistoriaClinica.objects.get(pk=history.pk)
            self.assertEqual((upgraded.enfermedad_actual, upgraded.diagnostico_provisional), ('', ''))
            patient = Estudiante.objects.get(pk=patient.pk)
            self.assertEqual((patient.lugar_nacimiento, patient.parentesco_emergencia, patient.telefono_emergencia), ('', '', ''))
            self.assertEqual(patient.telefono, '0001')
            self.assertIsNone(patient.tipo_paciente)
            with connection.cursor() as cursor:
                self.assertEqual(cursor.execute('PRAGMA foreign_key_check').fetchall(), [])
                self.assertEqual(cursor.execute('PRAGMA integrity_check').fetchall(), [('ok',)])
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())

    def test_option_migration_preserves_existing_columns_and_audits_with_unknown_flags(self):
        executor = MigrationExecutor(connection)
        executor.migrate([('Hisotria_clinica', '0006_attention_report_team')])
        old = executor.loader.project_state([('Hisotria_clinica', '0006_attention_report_team')]).apps
        Patient = old.get_model('Hisotria_clinica', 'Estudiante')
        History = old.get_model('Hisotria_clinica', 'HistoriaClinica')
        Audit = old.get_model('Hisotria_clinica', 'AuditoriaClinica')
        from LoginRegister.test_security import account
        from LoginRegister.models import Usuario
        doctor = account('options-migration@example.invalid', 'medico')
        patient = Patient.objects.create(nombre='Persona', apellido='Ficticia', cedula='OLD-OPTION-1', edad=77,
            edo_civil='Soltero', sexo='Masculino', direccion='Ficticia', contacto_emergencia='Ficticio', telefono='0000', fecha_nacimiento='2000-01-01')
        history = History.objects.create(estudiante=patient, medico_id=doctor.pk, fecha_consulta='2026-01-15',
            motivo_consulta='Ficticio', diagnostico='Ficticio', tratamiento='No implica Tto', version=3)
        Audit.objects.create(historia=history, usuario_id=doctor.pk, motivo='Ficticio', anteriores={'diagnostico': 'Anterior'}, nuevos={'diagnostico': 'Ficticio'})
        source = [Patient, History, Audit, Usuario]
        snapshots = [list(model.objects.order_by('pk').values()) for model in source]
        try:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
            from .models import Estudiante, HistoriaClinica, AuditoriaClinica
            from .daily_options import OPTION_CODES
            for model, rows in zip([Estudiante, HistoriaClinica, AuditoriaClinica, Usuario], snapshots):
                self.assertEqual(list(model.objects.order_by('pk').values(*rows[0])), rows)
            upgraded = HistoriaClinica.objects.get(pk=history.pk)
            self.assertTrue(all(getattr(upgraded, code) is None for code in OPTION_CODES))
            with connection.cursor() as cursor:
                self.assertEqual(cursor.execute('PRAGMA foreign_key_check').fetchall(), [])
                self.assertEqual(cursor.execute('PRAGMA integrity_check').fetchall(), [('ok',)])
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())

    def test_report_team_migration_preserves_existing_attentions_and_does_not_infer_nurse(self):
        executor = MigrationExecutor(connection)
        executor.migrate([('Hisotria_clinica', '0005_canonical_identity_key')])
        old = executor.loader.project_state([('Hisotria_clinica', '0005_canonical_identity_key')]).apps
        from LoginRegister.test_security import account
        nurse = account('legacy-report-nurse@example.invalid', 'enfermera')
        doctor = account('legacy-report-doctor@example.invalid', 'medico')
        Patient = old.get_model('Hisotria_clinica', 'Estudiante')
        Attention = old.get_model('Hisotria_clinica', 'Atencion')
        History = old.get_model('Hisotria_clinica', 'HistoriaClinica')
        Event = old.get_model('Hisotria_clinica', 'CambioEstadoAtencion')
        Audit = old.get_model('Hisotria_clinica', 'AuditoriaClinica')
        from django.utils import timezone
        patient = Patient.objects.create(nombre='Paciente', apellido='Ficticio', cedula='OLD-REPORT-1', edad=77,
            edo_civil='Soltero', sexo='Masculino', direccion='Ficticia', contacto_emergencia='Ficticio', telefono='0000', fecha_nacimiento='2000-01-01')
        attention = Attention.objects.create(paciente_id=patient.pk, fecha_hora_llegada=timezone.now(), motivo_visita='Ficticio',
            estado='atendido', registrada_por_id=nurse.pk, actualizada_por_id=doctor.pk, version=2)
        history = History.objects.create(estudiante_id=patient.pk, atencion_id=attention.pk, medico_id=doctor.pk,
            fecha_consulta='2026-01-15', motivo_consulta='Ficticio', diagnostico='Ficticio', tratamiento='Ficticio')
        Event.objects.create(atencion_id=attention.pk, usuario_id=doctor.pk, anterior='en_atencion', nuevo='atendido')
        Audit.objects.create(historia_id=history.pk, usuario_id=doctor.pk, motivo='Registro ficticio', nuevos={'diagnostico': 'Ficticio'})
        models = [Patient, Attention, History, Event, Audit]
        snapshots = [list(model.objects.order_by('pk').values()) for model in models]
        try:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
            from .models import Atencion, AuditoriaClinica, CambioEstadoAtencion, Estudiante, HistoriaClinica
            current = [Estudiante, Atencion, HistoriaClinica, CambioEstadoAtencion, AuditoriaClinica]
            for model, rows in zip(current, snapshots):
                self.assertEqual(list(model.objects.order_by('pk').values(*rows[0])), rows)
            upgraded = Atencion.objects.get(pk=attention.pk)
            self.assertIsNone(upgraded.enfermera_responsable_id)
            self.assertEqual(upgraded.turno, '')
            self.assertEqual(upgraded.registrada_por_id, nurse.pk)
            with connection.cursor() as cursor:
                self.assertEqual(cursor.execute('PRAGMA foreign_key_check').fetchall(), [])
                self.assertEqual(cursor.execute('PRAGMA integrity_check').fetchall(), [('ok',)])
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())

    def test_upgrade_preserves_all_old_columns_accounts_relations_and_audits(self):
        executor = MigrationExecutor(connection)
        executor.migrate([('Hisotria_clinica', '0002_estudiante_cedula'), ('LoginRegister', '0004_review_legacy_accounts')])
        old_apps = executor.loader.project_state([
            ('Hisotria_clinica', '0002_estudiante_cedula'), ('LoginRegister', '0004_review_legacy_accounts')]).apps
        Patient = old_apps.get_model('Hisotria_clinica', 'Estudiante')
        History = old_apps.get_model('Hisotria_clinica', 'HistoriaClinica')
        from LoginRegister.test_security import account
        from LoginRegister.models import AccountAudit, Usuario
        admin = account('admin-upgrade@example.invalid', 'administrador')
        doctor = account('doctor-upgrade@example.invalid', 'medico')
        AccountAudit.objects.create(actor=admin, target=doctor, action='approve', reason='Aprobación histórica ficticia', before={}, after={'authorized_role': 'medico'})
        first = Patient.objects.create(nombre='Paciente', apellido='Ficticio', cedula=' v-1001 ', edad=77,
            edo_civil='Soltero', sexo='Masculino', direccion='Ficticia', contacto_emergencia='Ficticio', telefono='0000', fecha_nacimiento='2000-01-01')
        second = Patient.objects.create(nombre='Paciente', apellido='Sin clasificación', cedula='', edad=99,
            edo_civil='Soltero', sexo='Masculino', direccion='Ficticia', contacto_emergencia='Ficticio', telefono='0000', fecha_nacimiento='1990-01-01')
        for patient in [first, second, first]:
            History.objects.create(estudiante=patient, fecha_consulta='2026-10-27', motivo_consulta='Ficticio', diagnostico='Original ficticio', tratamiento='Original ficticio')
        before_patients = list(Patient.objects.order_by('pk').values())
        before_histories = list(History.objects.order_by('pk').values())
        before_users = list(Usuario.objects.order_by('pk').values())
        before_audits = list(AccountAudit.objects.order_by('pk').values())
        try:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
            from .models import Atencion, AuditoriaClinica, AuditoriaPaciente, Estudiante, HistoriaClinica
            self.assertEqual(list(Estudiante.objects.order_by('pk').values(*before_patients[0])), before_patients)
            self.assertEqual(list(HistoriaClinica.objects.order_by('pk').values(*before_histories[0])), before_histories)
            self.assertEqual(list(Usuario.objects.order_by('pk').values()), before_users)
            self.assertEqual(list(AccountAudit.objects.order_by('pk').values()), before_audits)
            self.assertTrue(all(patient.tipo_paciente is None and patient.categoria_visible == 'Por verificar' for patient in Estudiante.objects.all()))
            self.assertFalse(HistoriaClinica.objects.filter(medico__isnull=False).exists())
            self.assertFalse(HistoriaClinica.objects.filter(atencion__isnull=False).exists())
            self.assertEqual(Atencion.objects.count(), 0)
            self.assertEqual(AuditoriaClinica.objects.count(), 0)
            self.assertEqual(AuditoriaPaciente.objects.count(), 0)
            with connection.cursor() as cursor:
                self.assertEqual(cursor.execute('PRAGMA integrity_check').fetchall(), [('ok',)])
                self.assertEqual(cursor.execute('PRAGMA foreign_key_check').fetchall(), [])
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
