"""Create a review PDF using an IN-MEMORY database and fictitious data only."""
from datetime import date, datetime, timezone as utc_timezone
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
    from Hisotria_clinica.daily_options import OPTION_CODES
    from Hisotria_clinica.models import Atencion
    from Hisotria_clinica.pdf_reports import daily_register_pdf
    from Hisotria_clinica.services import create_history, register_arrival, register_patient, transition_attention
    call_command('migrate', interactive=False, verbosity=0)
    people = {}
    for role, name in [('medico', 'Médico ficticio'), ('enfermera', 'Enfermera ficticia')]:
        people[role] = Usuario.objects.create_user(email=role+'@ficticio.invalid', password=secrets.token_urlsafe(24),
            nombre=name, apellido='Demostración', approval_status='aprobado', authorized_role=role)
    nurse, doctor = people['enfermera'], people['medico']
    for index in range(18):
        patient = register_patient(actor=nurse, data=dict(nombre='Paciente ficticio', apellido=f'Muestra {index+1:02}',
            cedula=f'DEMO-{7001+index}', tipo_paciente='externo', fecha_nacimiento=date(2000, 1, 1),
            sexo='Femenino', edo_civil='Sin especificar', direccion='Ficticia', telefono='0000', contacto_emergencia='Ficticio'))
        attention = register_arrival(actor=nurse, patient_id=patient.pk, arrival=timezone.now(),
            reason='Prueba sintética', nurse_id=nurse.pk, shift='Mañana')
        transition_attention(actor=nurse, attention_id=attention.pk, target='en_atencion', expected_version=0)
        options = {code: index == 0 or (index+offset) % 3 == 0 for offset, code in enumerate(OPTION_CODES)}
        create_history(actor=doctor, patient_id=patient.pk, attention_id=attention.pk,
            data=dict(fecha_consulta=date(2026, 10, 28), motivo_consulta='Muestra ficticia',
                      diagnostico='Diagnóstico ficticio', tratamiento='Tratamiento ficticio', **options))
        Atencion.objects.filter(pk=attention.pk).update(actualizada_en=datetime(2026, 10, 28, 12, tzinfo=utc_timezone.utc))
    output = repository / 'output/pdf/FOR-SSS-02_demo.pdf'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(daily_register_pdf(actor=doctor, start=date(2026, 10, 27), end=date(2026, 10, 28)))
    print('PDF ficticio, 3 páginas (fecha vacía y 18 consultas):', output)
    print('La base original no se abrió ni migró.')


if __name__ == '__main__':
    main()
