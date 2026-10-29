"""Verify 0003/0004 on physical SQLite files containing only synthetic data.

Does not connect to the repository database. Temporary fixtures are retained so
the operator can inspect them. Never use these files as an operational database.
"""
import hashlib
from io import StringIO
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from unittest.mock import patch


def main():
    repository = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository))
    original = repository / 'db.sqlite3'
    original_digest = hashlib.sha256(original.read_bytes()).digest() if original.exists() else None
    directory = Path(tempfile.mkdtemp(prefix='.uptag-upgrade-', dir=repository)).resolve()
    source = directory / 'synthetic-baseline.sqlite3'
    trial = directory / 'synthetic-trial.sqlite3'
    os.environ['DJANGO_SETTINGS_MODULE'] = 'config.test_settings'
    from django.conf import settings
    settings.DATABASES['default']['NAME'] = str(source)
    import django
    django.setup()
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor
    from django.core.management import call_command
    from django.contrib.auth.hashers import PBKDF2PasswordHasher

    executor = MigrationExecutor(connection)
    targets = [node for node in executor.loader.graph.leaf_nodes() if node[0] not in ['LoginRegister', 'Hisotria_clinica']]
    targets.extend([('LoginRegister', '0002_alter_usuario_cargo'), ('Hisotria_clinica', '0002_estudiante_cedula')])
    executor.migrate(targets)
    apps = executor.loader.project_state(targets).apps
    User = apps.get_model('LoginRegister', 'Usuario')
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    ContentType = apps.get_model('contenttypes', 'ContentType')
    LogEntry = apps.get_model('admin', 'LogEntry')
    cargos = ['Medico', 'medico', 'Enfermero/a', 'enfermero', 'MEDICO', 'Enfermera', '', 'Valor ambiguo']
    encoded = PBKDF2PasswordHasher().encode('Synthetic-Previous-Password-2026!', 'syntheticSalt', iterations=12000)
    users = [User.objects.create(email=f'fixture{index}@example.invalid', password=encoded,
        cargo=cargo, nombre='Usuario ficticio', apellido=str(index), is_active=index != 1,
        is_superuser=index == 7, is_staff=index == 7) for index, cargo in enumerate(cargos)]
    content_type = ContentType.objects.create(app_label='Hisotria_clinica', model='estudiante')
    permission = Permission.objects.create(content_type=content_type, codename='view_estudiante', name='Permiso ficticio')
    group = Group.objects.create(name='Grupo ficticio')
    group.permissions.add(permission)
    users[0].groups.add(group)
    users[0].user_permissions.add(permission)
    LogEntry.objects.create(user_id=users[0].pk, content_type_id=content_type.pk,
        object_id='1', object_repr='Registro ficticio', action_flag=1, change_message='Solo prueba')
    Estudiante = apps.get_model('Hisotria_clinica', 'Estudiante')
    HistoriaClinica = apps.get_model('Hisotria_clinica', 'HistoriaClinica')
    patient = Estudiante.objects.create(nombre='Paciente', apellido='Ficticio', cedula='SYNTHETIC-AUDIT', edad=26,
        edo_civil='Soltero', sexo='Masculino', direccion='Ficticia', contacto_emergencia='Ficticio', telefono='0000', fecha_nacimiento='2000-01-01')
    HistoriaClinica.objects.create(estudiante=patient, fecha_consulta='2026-10-27', motivo_consulta='Ficticio', diagnostico='Ficticio', tratamiento='Ficticio')
    tables = ['LoginRegister_usuario', 'LoginRegister_usuario_groups', 'LoginRegister_usuario_user_permissions',
        'auth_group', 'auth_group_permissions', 'django_admin_log',
        'Hisotria_clinica_estudiante', 'Hisotria_clinica_historiaclinica']

    def snapshot(database, columns=None):
        rows, observed = {}, {}
        for table in tables:
            names = columns[table] if columns else [row[1] for row in database.execute(f'PRAGMA table_info("{table}")')]
            observed[table] = names
            quoted = ','.join('"' + name + '"' for name in names)
            rows[table] = list(database.execute(f'SELECT {quoted} FROM "{table}" ORDER BY id'))
        return rows, observed

    connection.close()
    with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as baseline:
        baseline.execute('PRAGMA query_only=ON')
        before, columns = snapshot(baseline)
        with sqlite3.connect(trial) as destination:
            baseline.backup(destination)
    source_digest = hashlib.sha256(source.read_bytes()).digest()
    connection.settings_dict['NAME'] = str(trial)
    settings.DATABASES['default']['NAME'] = str(trial)
    MigrationExecutor(connection).migrate([('LoginRegister', '0003_account_approval_schema')])
    with connection.cursor() as cursor:
        cursor.execute('SELECT DISTINCT approval_status FROM LoginRegister_usuario')
        assert cursor.fetchall() == [('legacy',)]
    try:
        MigrationExecutor(connection).migrate([('LoginRegister', '0004_review_legacy_accounts')])
    except RuntimeError as error:
        assert 'administrador verificado' in str(error)
    else:
        raise AssertionError('The administrator guard did not stop migration')
    print('0004: blocked without a verified administrator, as expected.')
    password = 'Synthetic-Initial-Administrator-2026!'
    with patch('LoginRegister.management.commands.bootstrap_admin.getpass', side_effect=[password, password]):
        call_command('bootstrap_admin', email='new-admin@example.invalid', nombre='Administrador', apellido='Ficticio', stdout=StringIO())
    with patch('LoginRegister.management.commands.bootstrap_admin.getpass', return_value=password):
        call_command('bootstrap_admin', email='new-admin@example.invalid', verify=True, stdout=StringIO())
    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())
    from LoginRegister.models import Usuario
    mapping = {'Medico': 'medico', 'medico': 'medico', 'Enfermero/a': 'enfermera', 'enfermero': 'enfermera'}
    for previous in users:
        current = Usuario.objects.get(pk=previous.pk)
        assert current.approval_status == 'pendiente' and current.authorized_role == ''
        assert current.requested_role == mapping.get(previous.cargo, '')
        assert current.password == encoded
    with sqlite3.connect(trial.as_uri() + '?mode=ro', uri=True) as upgraded:
        after, _ = snapshot(upgraded, columns)
        after['LoginRegister_usuario'] = [row for row in after['LoginRegister_usuario'] if row[0] in {user.pk for user in users}]
        assert before == after
        assert upgraded.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
        assert upgraded.execute('PRAGMA foreign_key_check').fetchall() == []
    from Hisotria_clinica.models import Atencion, Estudiante as CurrentPatient, HistoriaClinica as CurrentHistory
    assert not CurrentPatient.objects.filter(tipo_paciente__isnull=False).exists()
    assert not CurrentHistory.objects.filter(medico__isnull=False).exists()
    assert not CurrentHistory.objects.filter(atencion__isnull=False).exists()
    assert Atencion.objects.count() == 0
    print('Old patients remain unverified; no historical doctors or arrivals invented.')
    from django.test import Client
    client = Client()
    assert client.post('/', {'username': 'new-admin@example.invalid', 'password': password}).status_code == 302
    assert client.get('/cuentas/').status_code == 200
    connection.close()
    assert hashlib.sha256(source.read_bytes()).digest() == source_digest
    if original_digest is not None:
        assert hashlib.sha256(original.read_bytes()).digest() == original_digest
    print('8 historical accounts: original columns, password hashes, IDs and flags preserved.')
    print('Groups, individual/group permissions and administrative relationships preserved.')
    print('Synthetic patients and histories unchanged; integrity and foreign keys valid.')
    print('New administrator: login and /cuentas/ verified on the trial file.')
    print('Synthetic baseline and repository db.sqlite3 unchanged.')
    print('Retained synthetic fixtures:', directory)


if __name__ == '__main__':
    main()
