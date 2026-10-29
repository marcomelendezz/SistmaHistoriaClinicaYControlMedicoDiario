"""Approve a fictitious FOR-SSS-07 using only a new IN-MEMORY SQLite."""
from datetime import date
import os
from pathlib import Path
import secrets
import sys


def main():
    repository = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository))
    os.environ['DJANGO_SETTINGS_MODULE'] = 'config.test_settings'
    os.environ['DJANGO_TIME_ZONE'] = 'America/Caracas'
    import django
    django.setup()
    from django.conf import settings
    if settings.DATABASES['default']['NAME'] != ':memory:':
        raise SystemExit('Solo se permite SQLite en memoria.')
    from django.core.management import call_command
    from django.utils import timezone
    from LoginRegister.models import Usuario
    from Hisotria_clinica.reposos import create_reposo_draft, review_reposo, approve_reposo, issued_reposo_pdf
    from Hisotria_clinica.reports import REPORT_ZONE
    from Hisotria_clinica.services import create_history, register_arrival, register_patient, transition_attention
    call_command('migrate', interactive=False, verbosity=0)
    doctor = Usuario.objects.create_user(email='medico@ficticio.invalid', password=secrets.token_urlsafe(24),
        nombre='Médico', apellido='Ficticio', approval_status='aprobado', authorized_role='medico')
    patient = register_patient(actor=doctor, data=dict(nombre='Paciente de muestra', apellido='Ficticio', cedula='DEMO-9001',
        tipo_paciente='estudiante', pnf='PNF ficticio', fecha_nacimiento=date(2000, 5, 8), sexo='Femenino',
        edo_civil='Sin especificar', direccion='Ficticia', telefono='0000000000', contacto_emergencia='Ficticio'))
    attention = register_arrival(actor=doctor, patient_id=patient.pk, arrival=timezone.now(), reason='Muestra ficticia')
    transition_attention(actor=doctor, attention_id=attention.pk, target='en_atencion', expected_version=0)
    today = timezone.localdate(timezone=REPORT_ZONE)
    history = create_history(actor=doctor, patient_id=patient.pk, attention_id=attention.pk,
        data=dict(fecha_consulta=today, motivo_consulta='Muestra ficticia', diagnostico='Diagnóstico ficticio', tratamiento='Tratamiento ficticio'))
    draft = create_reposo_draft(actor=doctor, history_id=history.pk,
        data={'motivo_reposo': 'Motivo clínico ficticio, exclusivamente para revisar el documento.\n'
              'Esta muestra no corresponde a una persona real.', 'dias': 3, 'fecha_inicio': today})
    _, _, _, token = review_reposo(actor=doctor, reposo_id=draft.pk)
    issued = approve_reposo(actor=doctor, reposo_id=draft.pk, expected_revision=0, review_token=token, confirmed=True)
    _, content = issued_reposo_pdf(actor=doctor, reposo_id=issued.pk)
    output = repository / 'output/pdf/FOR-SSS-07_demo.pdf'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(content)
    print('PDF ficticio aprobado y leído desde su versión guardada:', output)
    print('SHA-256:', issued.pdf_sha256)
    print('La base original no se abrió ni migró.')


if __name__ == '__main__':
    main()
