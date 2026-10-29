"""Render a fictitious FOR-SSS-04 with a fresh IN-MEMORY SQLite only."""
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
    from Hisotria_clinica.pdf_histories import clinical_history_pdf
    from Hisotria_clinica.services import create_history, register_arrival, register_patient, transition_attention
    call_command('migrate', interactive=False, verbosity=0)
    nurse = Usuario.objects.create_user(email='enfermera@ficticio.invalid', password=secrets.token_urlsafe(24),
        nombre='Enfermera', apellido='Ficticia', approval_status='aprobado', authorized_role='enfermera')
    doctor = Usuario.objects.create_user(email='medico@ficticio.invalid', password=secrets.token_urlsafe(24),
        nombre='Médico', apellido='Ficticio', approval_status='aprobado', authorized_role='medico')
    patient = register_patient(actor=nurse, data=dict(nombre='Paciente de muestra', apellido='Ficticio',
        cedula='DEMO-8001', tipo_paciente='estudiante', pnf='PNF de demostración', fecha_nacimiento=date(2000, 5, 8),
        lugar_nacimiento='Santa Ana de Coro', sexo='Femenino', edo_civil='Sin especificar',
        direccion='Dirección ficticia para revisión', telefono='0000000000', contacto_emergencia='Contacto ficticio',
        parentesco_emergencia='Familiar ficticio', telefono_emergencia='0000000001'))
    attention = register_arrival(actor=nurse, patient_id=patient.pk, arrival=timezone.now(), reason='Consulta de demostración')
    transition_attention(actor=nurse, attention_id=attention.pk, target='en_atencion', expected_version=0)
    history = create_history(actor=doctor, patient_id=patient.pk, attention_id=attention.pk, data=dict(
        fecha_consulta=timezone.localdate(), motivo_consulta='Motivo de consulta ficticio para comprobar el formato institucional.',
        enfermedad_actual='Descripción clínica de demostración, sin datos de una persona real.\n'
                          'Texto sintético para revisar acentos, distribución y legibilidad.',
        diagnostico_provisional='Diagnóstico provisional ficticio, exclusivamente para revisar la plantilla.',
        diagnostico='Campo interno que no corresponde a esta hoja.', tratamiento='Campo interno no impreso.'))
    output = repository / 'output/pdf/FOR-SSS-04_demo.pdf'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(clinical_history_pdf(actor=doctor, history_id=history.pk))
    print('PDF de una hoja con datos ficticios:', output)
    print('La base original no se abrió ni migró.')


if __name__ == '__main__':
    main()
