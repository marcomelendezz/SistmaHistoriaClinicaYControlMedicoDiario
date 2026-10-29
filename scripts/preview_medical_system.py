"""Start a localhost-only demo on a NEW SQLite containing synthetic data only."""
import argparse
from datetime import date
import os
from pathlib import Path
import secrets
import socket
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8001)
    parser.add_argument('--prepare-only', action='store_true')
    options = parser.parse_args()
    if not options.prepare_only:
        try:
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', options.port))
        except OSError as exc:
            raise SystemExit('No se pudo abrir el puerto local. Elige otro con --port y no uses un servidor que ya esté en ejecución.') from exc
    repository = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository))
    directory = Path(tempfile.mkdtemp(prefix='.uptag-demo-', dir=repository)).resolve()
    database = directory / 'demo.sqlite3'
    # Never consume an existing DB path or shared operational secret.
    os.environ.update(DJANGO_SETTINGS_MODULE='config.settings', DJANGO_DB_PATH=str(database),
        DJANGO_SECRET_KEY=secrets.token_urlsafe(64), DJANGO_DEBUG='true',
        DJANGO_ALLOWED_HOSTS='localhost,127.0.0.1', DJANGO_TIME_ZONE='America/Caracas',
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    from django.conf import settings
    settings.SESSION_COOKIE_NAME = 'uptag_demo_session'
    settings.CSRF_COOKIE_NAME = 'uptag_demo_csrf'
    import django
    django.setup()
    from django.core.management import call_command
    from django.utils import timezone
    from LoginRegister.models import AccountAudit, Usuario
    from Hisotria_clinica.models import Estudiante
    from Hisotria_clinica.daily_options import OPTION_CODES
    from Hisotria_clinica.services import create_history, register_arrival, register_patient, transition_attention

    call_command('migrate', interactive=False, verbosity=0)
    credentials = []
    people = {}
    for role, label in [('administrador', 'Administrador'), ('enfermera', 'Enfermera'), ('medico', 'Médico')]:
        password = secrets.token_urlsafe(18)
        email = role + '@demo.invalid'
        people[role] = Usuario.objects.create_user(email=email, password=password, nombre=label, apellido='Demostración',
            approval_status='aprobado', authorized_role=role, cargo='')
        credentials.append((label, email, password))
    admin = people['administrador']
    for user in people.values():
        AccountAudit.objects.create(actor=admin, target=user, action='demo_setup',
            reason='Cuenta ficticia creada exclusivamente en una base nueva de demostración.', after={'authorized_role': user.authorized_role})
    nurse, doctor = people['enfermera'], people['medico']
    patients = []
    for index, (category, label) in enumerate(Estudiante.Tipo.choices):
        data = dict(nombre='Paciente demo', apellido=f'Muestra {index+1:02}', cedula=f'DEMO-{1001+index}', tipo_paciente=category,
            fecha_nacimiento=date(1990+index, 1, 1), edo_civil='Sin especificar', sexo='Femenino',
            direccion='Dirección ficticia', telefono='0000000000', contacto_emergencia='Contacto ficticio',
            lugar_nacimiento='Coro', parentesco_emergencia='Familiar ficticio', telefono_emergencia='0000000001')
        if category == 'estudiante':
            data['pnf'] = 'PNF de demostración'
        elif category != 'externo':
            data['cargo_laboral'] = 'Cargo de demostración'
        patients.append(register_patient(actor=nurse, data=data))
    Estudiante.objects.create(nombre='Ficha histórica', apellido='Ficticia por verificar', cedula='DEMO-ANTIGUO',
        fecha_nacimiento=date(1990, 1, 1), edad=77, edo_civil='Sin especificar', sexo='Masculino',
        direccion='Ficticia', telefono='0000', contacto_emergencia='Ficticio')
    for index in range(4):
        attention = register_arrival(actor=nurse, patient_id=patients[index].pk, arrival=timezone.now(), reason='Visita ficticia de demostración',
            nurse_id=nurse.pk if index in [0, 2] else None, shift='Mañana' if index in [0, 2] else '')
        if index in [1, 2]:
            attention = transition_attention(actor=nurse, attention_id=attention.pk, target='en_atencion', expected_version=0)
        if index == 2:
            create_history(actor=doctor, patient_id=patients[index].pk, attention_id=attention.pk,
                data=dict(fecha_consulta=timezone.localdate(), motivo_consulta='Consulta ficticia', diagnostico='Diagnóstico ficticio', tratamiento='Texto de demostración', observaciones='Solo para comprobar la interfaz.', enfermedad_actual='Enfermedad actual ficticia.', diagnostico_provisional='Provisional ficticio.', **dict.fromkeys(OPTION_CODES, True)))
        if index == 3:
            transition_attention(actor=nurse, attention_id=attention.pk, target='cancelado', expected_version=0)
    external_visit = register_arrival(actor=nurse, patient_id=patients[4].pk, arrival=timezone.now(),
        reason='Visita externa ficticia', nurse_id=nurse.pk, shift='Tarde')
    transition_attention(actor=nurse, attention_id=external_visit.pk, target='en_atencion', expected_version=0)
    create_history(actor=doctor, patient_id=patients[4].pk, attention_id=external_visit.pk,
        data=dict(fecha_consulta=timezone.localdate(), motivo_consulta='Consulta externa ficticia',
                  diagnostico='Diagnóstico ficticio', tratamiento='Texto ficticio', observaciones='Solo prueba de reportes.',
                  enfermedad_actual='Descripción clínica ficticia.', diagnostico_provisional='Provisional ficticio.', lab=True, ref=True))
    # Two independent fictitious consultations: one draft, one approved specimen.
    from Hisotria_clinica.models import HistoriaClinica
    from Hisotria_clinica.reposos import create_reposo_draft, review_reposo, approve_reposo
    for index, history in enumerate(HistoriaClinica.objects.order_by('pk')):
        draft = create_reposo_draft(actor=doctor, history_id=history.pk, data={
            'motivo_reposo': 'Motivo de reposo ficticio para revisar el sistema.',
            'dias': 3, 'fecha_inicio': timezone.localdate()})
        if index == 1:
            _, _, _, token = review_reposo(actor=doctor, reposo_id=draft.pk)
            approve_reposo(actor=doctor, reposo_id=draft.pk, expected_revision=0, review_token=token, confirmed=True)
    print('\nDEMONSTRACION: TODOS LOS DATOS Y CUENTAS SON FICTICIOS.', flush=True)
    print('SQLite nueva:', database, flush=True)
    for label, email, password in credentials:
        print(f'{label}: {email} | contraseña: {password}', flush=True)
    print(f'URL: http://127.0.0.1:{options.port}/', flush=True)
    print('Las claves son aleatorias. Cada ejecución crea otra demo; db.sqlite3 no se abre ni se migra.', flush=True)
    print('Zona horaria de la demo: America/Caracas.', flush=True)
    if not options.prepare_only:
        call_command('runserver', f'127.0.0.1:{options.port}', use_reloader=False)


if __name__ == '__main__':
    main()
