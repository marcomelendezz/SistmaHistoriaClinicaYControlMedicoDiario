# Revisión y ensayo seguro de las migraciones 0003 y 0004

**Actualización:** con las correcciones de pacientes y atención hay migraciones
adicionales. Antes de iniciar el servidor también deben aplicarse, sobre la copia,
`Hisotria_clinica.0003`, `0004`, `0005` y `LoginRegister.0005`. Sigue la
[guía vigente](CORRECCIONES_PACIENTES_ATENCION.md) para completar toda la
actualización; este documento describe la secuencia inicial de autenticación.

## Diagnóstico y conservación

`no such column: LoginRegister_usuario.requested_role` significa que se está
ejecutando el modelo nuevo sobre una base con el esquema antiguo. Con 0001 y
0002 aplicadas, esa columna aún no existe. No se resuelve borrando SQLite,
recreando tablas, generando otra migración ni usando `--fake`.

La revisión del 27 de octubre de 2026 comprobó:

- `0003_account_approval_schema` añade seis campos al usuario y la tabla de
  auditoría. No contiene operaciones que borren usuarios, pacientes o historias.
  SQLite puede reconstruir internamente la tabla para añadir los campos y la
  relación; por eso se verificó la conservación de filas y relaciones.
- `approval_status` se incorpora con `legacy` para las filas existentes. El
  `AlterField` posterior fija `pendiente` como valor predeterminado para las
  cuentas nuevas; no convierte en pendientes las filas `legacy` existentes.
- `0004_review_legacy_accounts` procesa exclusivamente cuentas `legacy`. Conserva
  sus columnas originales: hash de contraseña, identificador, correo, `cargo`,
  indicadores de actividad y privilegios técnicos, entre otras. Mantiene sus
  grupos, permisos y relaciones con otros registros. No modifica información
  médica.
- Antes de procesar esas cuentas, 0004 exige un administrador activo, aprobado,
  con rol `administrador` y un evento `bootstrap_verified`. Si falta, falla antes
  de alterar las cuentas antiguas. La operación es transaccional.
- La reversión de 0004 solo restaura cuentas que siguen sin revisión y registra
  el hecho sin borrar auditoría. No revierte decisiones administrativas
  posteriores. No se recomienda revertir 0003, porque retiraría campos y auditoría.

El ensayo físico utilizó dos SQLite independientes con datos ficticios, nunca una
copia con datos reales: ocho usuarios de roles diversos, un usuario inactivo,
un superusuario, grupos, permisos individuales y de grupo, relaciones del log
administrativo, un paciente y una historia. Se compararon todas sus columnas
originales antes/después, se ejecutaron `integrity_check` y `foreign_key_check`,
y se probó el login y acceso a `/cuentas/` del administrador nuevo. El resultado
fue correcto; el SQLite original del repositorio conservó su huella SHA-256.

Resultado de pruebas tras la corrección del comando: **12 pruebas específicas
aprobadas y suite completa de 54 pruebas aprobada**, con Django 5.2.18. No hay
cambios de modelos sin migración ni errores de `check` o `git diff --check`.
Las migraciones 0003 y 0004 se conservaron sin modificaciones durante esta revisión.

El ensayo es reproducible con:

```powershell
.\.venv-phase1\Scripts\python.exe -B scripts\verify_account_migrations_synthetic.py
```

El script solo crea datos ficticios en archivos temporales y los conserva para
inspección. No conecta a `db.sqlite3`; únicamente calcula su huella de archivo
antes/después si existe. No utilizar sus credenciales ficticias en operación.

## Cómo quedan las cuentas antiguas

| `cargo` antiguo, conservado literalmente | `requested_role` después de 0004 |
| --- | --- |
| `Medico` o `medico` | `medico` |
| `Enfermero/a` o `enfermero` | `enfermera` |
| Cualquier otro valor, incluido vacío | Vacío; requiere revisión |

La comparación de roles es exacta: `MEDICO`, `Médico`, `Enfermera`, espacios
adicionales u otros valores no se convierten automáticamente. No se corrigen ni
se pierden: permanecen en `cargo` como evidencia para la revisión administrativa.

Todas las cuentas antiguas procesadas quedan con `approval_status='pendiente'`
y `authorized_role=''`, incluso si su cargo resulta reconocible o si tenían
`is_staff`, `is_superuser` o grupos. El rol solicitado no concede facultades.
`is_active` se conserva: una cuenta inactiva no se reactiva por migrar.

El administrador designado explícitamente antes de 0004 ya está `aprobado`, por
lo que esa migración no lo procesa como cuenta antigua. Desde `/cuentas/` podrá
verificar y aprobar al resto. El administrador no obtiene permisos de escritura
clínica por esa condición. La aprobación de una cuenta mediante esa pantalla sí
puede activarla, como decisión administrativa posterior a las migraciones.

**No intentar iniciar sesión entre 0003 y la creación del administrador.**
Mantener el servidor detenido durante todo el procedimiento. Crear un
superusuario con `createsuperuser` no sustituye la aprobación institucional.

Se recomienda crear un administrador nuevo para el ensayo. Para designar una
cuenta existente se admite `bootstrap_admin --designate-existing`, verificando
su contraseña actual; nunca se debe utilizar un correo ambiguo. El comando
rechaza coincidencias múltiples al ignorar mayúsculas. Durante esta revisión se
corrigió la verificación para que tampoco actualice automáticamente un hash
antiguo; se añadió y aprobó una prueba específica para esa conservación.

## Ensayo sobre una copia de tu SQLite: PowerShell

Estos comandos son para que los ejecute el operador. No se ejecutaron contra
tu base original durante la revisión. Las copias contendrán datos personales si
el origen los contiene: mantenerlas privadas, fuera de Git y de carpetas públicas.
No modificar pacientes ni historias durante el ensayo; usar el administrador
nuevo para validar autenticación y gestión de cuentas.

### 1. Detener el servidor y preparar esta consola

Detener `runserver` con Ctrl+C en su consola y cualquier otro escritor de SQLite.
Usar una consola PowerShell nueva para este ensayo; las variables son temporales
y no cambian la configuración de otras consolas.

```powershell
$ErrorActionPreference = 'Stop'
$repoRoot = 'C:\Users\wilfr\OneDrive\Datos adjuntos\Documents\GitHub\SistmaHistoriaClinicaYControlMedicoDiario'
Set-Location -LiteralPath $repoRoot
$uptagPython = Join-Path $repoRoot '.venv-phase1\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $uptagPython)) { throw 'No existe el entorno .venv-phase1. Selecciona el Python donde instalaste requirements.txt.' }

function Invoke-UptagPython {
    & $uptagPython @args
    if ($LASTEXITCODE -ne 0) { throw 'El comando Python falló. Detente y revisa el error antes de continuar.' }
}

# Si tu servidor utiliza otra SQLite, sustituye ESTA ruta por la ruta real.
$originalDb = (Resolve-Path -LiteralPath (Join-Path $repoRoot 'db.sqlite3')).Path
$originalHash = (Get-FileHash -LiteralPath $originalDb -Algorithm SHA256).Hash
$trialRoot = Join-Path $env:LOCALAPPDATA ('UPTAG\MigrationCheck\' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $trialRoot | Out-Null

$env:UPTAG_SOURCE_DB = $originalDb
$env:UPTAG_BASELINE_DB = Join-Path $trialRoot 'antes.sqlite3'
$env:UPTAG_TRIAL_DB = Join-Path $trialRoot 'ensayo.sqlite3'

$env:DJANGO_SETTINGS_MODULE = 'config.settings'
if (-not $env:DJANGO_SECRET_KEY) {
    $env:DJANGO_SECRET_KEY = Invoke-UptagPython -B -c "import secrets; print(secrets.token_urlsafe(64))"
}
$env:DJANGO_DEBUG = 'true'
$env:DJANGO_ALLOWED_HOSTS = '127.0.0.1,localhost'
$env:EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
```

La clave generada no se muestra y solo vive en esta consola; si ya existe una
clave privada configurada se conserva. No reutilizar los secretos publicados.
No utilizar `config.test_settings` para el ensayo interactivo: esa configuración
fuerza memoria y no abriría la copia elegida. La consola usa `config.settings`.

### 2. Crear una copia base y una copia de trabajo sin sobrescribir archivos

Se usa el respaldo de SQLite con el origen en modo de solo lectura; esto evita
ignorar transacciones que pudieran estar en un archivo WAL. No copiar solo el
archivo `.sqlite3` mientras esté siendo escrito.

```powershell
@'
import os, sqlite3
from pathlib import Path

def backup(source_name, destination_name):
    source = Path(os.environ[source_name]).resolve(strict=True)
    destination = Path(os.environ[destination_name]).resolve()
    if source == destination:
        raise SystemExit('Origen y destino deben ser distintos.')
    with destination.open('xb'):
        pass  # Refuse to overwrite an existing file.
    with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as src:
        src.execute('PRAGMA query_only=ON')
        if src.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise SystemExit('El origen no supera integrity_check. Detenerse.')
        if src.execute('PRAGMA foreign_key_check').fetchone() is not None:
            raise SystemExit('El origen tiene relaciones inconsistentes. Detenerse.')
        with sqlite3.connect(str(destination)) as dst:
            src.backup(dst)

backup('UPTAG_SOURCE_DB', 'UPTAG_BASELINE_DB')
backup('UPTAG_BASELINE_DB', 'UPTAG_TRIAL_DB')
print('Copias independientes creadas; origen abierto solo para lectura.')
'@ | & $uptagPython -B -
if ($LASTEXITCODE -ne 0) { throw 'No continuar: la copia falló.' }

$env:DJANGO_DB_PATH = $env:UPTAG_TRIAL_DB
Write-Host ('SQLite de ensayo: ' + $env:DJANGO_DB_PATH)
Invoke-UptagPython -B manage.py shell --settings=config.settings --command "from django.conf import settings; print(settings.DATABASES['default']['NAME'])"
Invoke-UptagPython -B manage.py showmigrations LoginRegister --settings=config.settings
Invoke-UptagPython -B manage.py showmigrations --plan --settings=config.settings
```

Confirmar que se muestra `ensayo.sqlite3` y que 0001/0002 están aplicadas mientras
0003/0004 siguen pendientes. Si no coincide, detenerse y revisar la selección de
base. La copia `antes.sqlite3` debe permanecer sin migrar.
Si el plan general muestra migraciones pendientes de otras aplicaciones, revisar
sus efectos por separado antes de iniciar el servidor; estas órdenes no las
aplican indiscriminadamente.

### 3. Aplicar 0003 y establecer al administrador del ensayo

```powershell
Invoke-UptagPython -B manage.py migrate LoginRegister 0003 --plan --settings=config.settings
Invoke-UptagPython -B manage.py migrate LoginRegister 0003 --settings=config.settings

$initialAdminEmail = Read-Host 'Correo NUEVO para el administrador del ensayo (por ejemplo admin.ensayo@example.invalid)'
Invoke-UptagPython -B manage.py bootstrap_admin --email $initialAdminEmail --nombre Administrador --apellido Ensayo --settings=config.settings
Invoke-UptagPython -B manage.py bootstrap_admin --email $initialAdminEmail --verify --settings=config.settings
```

Introducir una contraseña propia cuando el comando la solicite; no aparece en
pantalla ni se pasa por argumentos. La nueva exige al menos 16 caracteres y los
demás validadores de Django. Debe aparecer la confirmación de administrador
verificado en ambas órdenes antes de continuar. Si el correo ya existe, elegir
otro para este procedimiento; no sobrescribir cuentas antiguas.

La creación o designación no exige tener ya las tablas de Axes. Si estas existen,
el comando restablece los intentos de bloqueo de esa cuenta. No elimina usuarios
ni auditoría clínica. El administrador nuevo no tiene que ser `is_staff` para
administrar desde `/cuentas/`.

### 4. Aplicar 0004 exclusivamente a la copia

```powershell
Invoke-UptagPython -B manage.py migrate LoginRegister 0004 --plan --settings=config.settings
Invoke-UptagPython -B manage.py migrate LoginRegister 0004 --settings=config.settings
Invoke-UptagPython -B manage.py showmigrations LoginRegister --settings=config.settings
Invoke-UptagPython -B manage.py check --settings=config.settings
```

Confirmar las cuatro migraciones con `[X]`. No utilizar `--fake`, borrar tablas,
eliminar SQLite ni intentar forzar la migración si se detiene por falta de
administrador. Volver a verificar al administrador con el comando anterior.

### 5. Comparar conservación antes de probar el navegador

La siguiente comprobación abre ambas copias solo para lectura y no imprime
usuarios, correos, contraseñas ni datos clínicos. Verifica que todas las filas
originales y sus columnas sigan presentes, incluidas las relaciones. Permite las
filas administrativas nuevas, como el administrador y las migraciones, y exige
igualdad exacta en las tablas clínicas.

Ejecutarla **antes de iniciar sesión o aprobar cuentas**: esas operaciones
posteriores sí cambian legítimamente sesiones, `last_login` y autorizaciones.

```powershell
@'
from collections import Counter
import os, sqlite3
from pathlib import Path

def readonly(name):
    path = Path(os.environ[name]).resolve(strict=True)
    connection = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    connection.execute('PRAGMA query_only=ON')
    return connection

def quote(identifier):
    return '"' + identifier.replace('"', '""') + '"'

with readonly('UPTAG_BASELINE_DB') as before, readonly('UPTAG_TRIAL_DB') as after:
    tables = [row[0] for row in before.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    for table in tables:
        columns = [row[1] for row in before.execute('PRAGMA table_info(' + quote(table) + ')')]
        query = 'SELECT ' + ','.join(map(quote, columns)) + ' FROM ' + quote(table)
        original = Counter(before.execute(query))
        upgraded = Counter(after.execute(query))
        if original - upgraded:
            raise SystemExit('Hay filas originales modificadas o ausentes en: ' + table)
        if table.startswith('Hisotria_clinica_') and original != upgraded:
            raise SystemExit('Los datos clinicos difieren en: ' + table)
    if after.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
        raise SystemExit('La copia migrada no supera integrity_check.')
    if after.execute('PRAGMA foreign_key_check').fetchone() is not None:
        raise SystemExit('La copia migrada tiene relaciones inconsistentes.')
print('OK: datos originales conservados, datos clinicos identicos e integridad valida.')
'@ | & $uptagPython -B -
if ($LASTEXITCODE -ne 0) { throw 'No continuar: revisar la diferencia sin tocar el origen.' }

if ((Get-FileHash -LiteralPath $originalDb -Algorithm SHA256).Hash -ne $originalHash) {
    throw 'La huella del archivo original cambio. Revisar si otro proceso lo escribio.'
}
Write-Host 'La huella del archivo original permanece igual.'
```

### 6. Validar el acceso local sobre la copia

```powershell
& $uptagPython -B manage.py runserver 127.0.0.1:8001 --noreload --settings=config.settings
```

Abrir una ventana privada del navegador en `http://127.0.0.1:8001/`, iniciar sesión
con el administrador creado y visitar `http://127.0.0.1:8001/cuentas/`. Comprobar
las solicitudes pendientes y la auditoría sin editar registros médicos. El menú
de administración institucional está en `/cuentas/`; no confundirlo con el admin
genérico `/admin/`, que además exige `is_staff`.

La SQLite usada seguirá siendo `ensayo.sqlite3`. No cambiar `DJANGO_DB_PATH`
mientras el servidor está funcionando; detenerlo con Ctrl+C primero.

## Aplicación a tu entorno local de desarrollo

La opción que conserva el original intacto es **continuar trabajando localmente
con la copia ya migrada**, manteniendo `DJANGO_DB_PATH` en `ensayo.sqlite3`.
La clave y la ruta deben configurarse de nuevo si se abre otra consola.

Si, después del ensayo satisfactorio, decides aplicar las migraciones al SQLite
original de desarrollo, esta es la secuencia manual. No fue ejecutada durante la
revisión. No usarla con una base de producción. Mantener los escritores detenidos
y conservar `antes.sqlite3` como respaldo privado sin sobrescribirlo.

```powershell
# Solo despues de detener runserver y aprobar el ensayo.
# Conservar la funcion Invoke-UptagPython y variables preparadas arriba.
if ((Get-FileHash -LiteralPath $originalDb -Algorithm SHA256).Hash -ne $originalHash) {
    throw 'El origen cambio desde el respaldo. Crear un respaldo y ensayo nuevos antes de migrar.'
}
$env:DJANGO_DB_PATH = $originalDb
Invoke-UptagPython -B manage.py showmigrations LoginRegister --settings=config.settings
Invoke-UptagPython -B manage.py migrate LoginRegister 0003 --plan --settings=config.settings
Invoke-UptagPython -B manage.py migrate LoginRegister 0003 --settings=config.settings

$developmentAdminEmail = Read-Host 'Correo NUEVO del administrador local de desarrollo'
Invoke-UptagPython -B manage.py bootstrap_admin --email $developmentAdminEmail --nombre Administrador --apellido Local --settings=config.settings
Invoke-UptagPython -B manage.py bootstrap_admin --email $developmentAdminEmail --verify --settings=config.settings

Invoke-UptagPython -B manage.py migrate LoginRegister 0004 --plan --settings=config.settings
Invoke-UptagPython -B manage.py migrate LoginRegister 0004 --settings=config.settings
Invoke-UptagPython -B manage.py showmigrations LoginRegister --settings=config.settings
Invoke-UptagPython -B manage.py check --settings=config.settings
& $uptagPython -B manage.py runserver 127.0.0.1:8000 --noreload --settings=config.settings
```

Estos comandos suponen exactamente el estado comunicado: 0001 y 0002 aplicadas,
0003 y 0004 pendientes. No ejecutar una orden que apunte a 0003 si 0004 ya figura
aplicada: solicitaría una reversión. Si el estado difiere, revisar el plan antes
de continuar. No copiar la SQLite del ensayo sobre el original como atajo.

El administrador deberá verificar individualmente las cuentas antiguas antes de
aprobar sus facultades. No se concede autorización médica por un cargo histórico,
un grupo o una bandera de superusuario.
