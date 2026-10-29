# Correcciones de pacientes, aprobación y atención médica

La ampliación posterior de reportes web y la migración 0006 se documentan en
[Fase 2: reportes](FASE2_REPORTES.md). Los resultados de 87 pruebas que figuran
al final corresponden a esta revisión anterior; la suite ampliada tiene 114.

## Alcance entregado

Se conserva la arquitectura Django, la tabla y el modelo `Estudiante`, sus claves
primarias y la relación `HistoriaClinica.estudiante`. En pantalla se presentan
como pacientes. No se aplicaron migraciones a `db.sqlite3` ni se publicaron cambios.

Se implementan exactamente cinco categorías: Estudiante, Profesor, Personal
Obrero/Técnico, Personal Administrativo y Paciente Externo. Antiguos miembros sin
vínculo activo se registran como externos; no se creó una categoría adicional.

Las fichas antiguas reciben `tipo_paciente=NULL`, mostrado como **Por verificar**.
Es una ausencia de clasificación, no un sexto valor seleccionable. La migración
no supone que alguien siga siendo estudiante ni altera sus datos personales.
Las nuevas fichas exigen cédula y categoría. PNF es opcional para estudiantes y
cargo es opcional para los tres tipos de trabajadores. No se añadió dependencia
laboral porque no forma parte de los campos confirmados por el usuario.

Cambiar la categoría conserva el expediente, sus consultas y los datos
institucionales anteriores. Los campos que ya no corresponden se ocultan y dejan
de exigirse; no se borran automáticamente. El servidor aplica estas reglas aunque
se envíen campos ocultos mediante una petición directa.

La cédula histórica no puede alterarse desde la edición ordinaria. En nuevas
fichas se validan longitud, dígitos y separadores habituales. La búsqueda y el
control de duplicados reconocen mayúsculas/minúsculas, espacios exteriores y
variaciones de puntos/guiones. Una clave interna única protege los registros
nuevos; las cédulas antiguas y sus identificadores permanecen literales, sin
fusiones ni renumeraciones. No se infiere un prefijo de nacionalidad ausente.
Si ya existían expedientes equivalentes con formatos distintos, se conservan y
deben revisarse mediante un procedimiento institucional independiente.

La edad visible se calcula desde el nacimiento. El campo de edad histórico se
conserva: no se recalcula en las migraciones ni al cambiar únicamente la categoría.
En nuevas fichas y al corregir expresamente el nacimiento se calcula su valor.

## Operación y permisos

1. **Registrar Paciente** crea exclusivamente una ficha personal. No genera una
   llegada ni una historia. Enfermería y médicos aprobados pueden hacerlo.
2. **Nueva Consulta** busca una ficha existente y registra fecha/hora de llegada
   y motivo. El estado inicial es Pendiente. Enfermería y médicos pueden usarla.
3. En **Atenciones**, ambos pueden pasar de Pendiente a En atención o cancelar
   una atención abierta. Se conserva quién realizó cada transición y cuándo.
4. Solo el médico aprobado puede **Redactar historia**. Debe completar fecha,
   motivo, diagnóstico y tratamiento. Al guardar, la historia y la finalización
   como Atendido se registran en una sola transacción.
5. Las correcciones clínicas solo admiten médicos, exigen motivo y conservan
   anteriores/nuevos valores, responsable y fecha. Una edición desactualizada se
   rechaza mediante un número de versión para evitar sobrescribir otra corrección.

Solo hay una atención abierta por paciente, protegida también por una restricción
de SQLite. Un paciente puede volver después de completar o cancelar una visita.
Las atenciones canceladas permanecen registradas; no son consultas completadas.
No se pueden finalizar atenciones enviando directamente un cambio a `atendido`.

El administrador conserva lectura de pacientes, historias y atenciones. No puede
registrar llegadas ni escribir datos personales o clínicos por su condición de
administrador. Las banderas técnicas de superusuario no evitan estos controles.

La URL histórica de registro combinado conserva navegación por GET hacia el alta
personal, pero rechaza POST: no hay creación combinada oculta ni enlace duplicado.

En **Administrar cuentas**, el motivo administrativo es opcional para aprobar,
asignar rol o rechazar. Se conserva acción, responsable, fecha, rol anterior/nuevo
y activación interna. La columna independiente Activo se retiró; una cuenta
desactivada se identifica en su estado y sigue pudiendo activarse/desactivarse.
Este cambio no afecta al motivo obligatorio de las correcciones clínicas.

La interfaz conserva el logotipo original, blanco/verde oscuro/gris, iconos SVG
en el menú y Bootstrap existente. Los formularios se apilan en móvil y las tablas
se desplazan dentro de su contenedor sin ampliar toda la página.

## Migraciones nuevas y conservación

| Aplicación / migración | Efecto |
| --- | --- |
| `Hisotria_clinica.0003_patient_classification_audit` | Añade categoría nullable, PNF/cargo opcionales y auditoría personal. No clasifica pacientes antiguos. |
| `Hisotria_clinica.0004_attention_clinical_audit` | Añade atención, trazabilidad, médico/enlace opcionales y auditoría clínica. Protege la relación de historia con paciente frente a borrado en cascada. |
| `Hisotria_clinica.0005_canonical_identity_key` | Añade una clave interna única nullable; no rellena ni modifica las cédulas históricas. |
| `LoginRegister.0005_optional_administrative_reason` | Admite observación administrativa vacía; conserva los eventos previos. |

No se modificaron las migraciones anteriores de autenticación ni historias.
Las consultas antiguas quedan sin médico y atención asignados cuando esa
información no existía. No se crean llegadas, aprobaciones ni auditorías ficticias
para rellenar el pasado. El número de versión nuevo empieza en cero.

Las relaciones y auditorías nuevas usan PROTECT. La interfaz no ofrece borrado
definitivo. Revertir las migraciones que crean tablas de auditoría destruiría
esa información nueva: no es un procedimiento de recuperación autorizado.

SQLite serializa las escrituras. Se usan transacciones, restricciones únicas y
versiones para atender conflictos; no se depende exclusivamente de bloqueos de
filas que SQLite no proporciona. No hay cambio de motor ni dependencias nuevas.

## Visualizar sin tocar la base original

Desde PowerShell, con las dependencias de `requirements.txt` instaladas:

```powershell
Set-Location -LiteralPath 'C:\Users\wilfr\OneDrive\Datos adjuntos\Documents\GitHub\SistmaHistoriaClinicaYControlMedicoDiario'
.\.venv-phase1\Scripts\python.exe -B scripts\preview_medical_system.py --port 8002
```

El comando crea una carpeta `.uptag-demo-...` y **una SQLite nueva**. Ignora
cualquier `DJANGO_DB_PATH` de la consola y nunca abre el SQLite original. Aplica
las migraciones únicamente a esa base vacía y carga las cinco categorías, una
ficha histórica por verificar y atenciones en los cuatro estados, todo ficticio.

La terminal muestra correos y contraseñas aleatorias para médico, enfermera y
administrador. No hay credenciales predeterminadas reutilizables. Abrir:

```text
http://127.0.0.1:8002/
```

El script comprueba que el puerto esté disponible. Si está ocupado, utilizar otro
valor de `--port` y abrir exactamente la URL que muestra la terminal. Cada
ejecución crea otra demostración; no sobrescribe ni limpia bases anteriores.
Las carpetas de ensayo están excluidas de Git. Ctrl+C detiene el servidor.

La demostración solo escucha en localhost, utiliza correo en memoria y cookies
con nombres propios para separar sus sesiones de las del sistema operativo.
No utilizarla para atención real ni introducir datos personales reales.

Comprobar en el navegador:

- Enfermera: Registrar Paciente, campos por categoría, Nueva Consulta, búsqueda
  por cédula, llegada y En atención. No aparece la escritura clínica.
- Médico: lo anterior y Redactar historia; posteriormente Corregir con motivo.
- Administrador: lectura y administración de cuentas con observación opcional.
- Móvil: botón Menú, formularios de una columna y desplazamiento de tablas.

Para preparar otra base ficticia sin iniciar servidor:

```powershell
.\.venv-phase1\Scripts\python.exe -B scripts\preview_medical_system.py --prepare-only
```

## Ensayo sobre una copia privada de tu base

No se ejecutó esta operación sobre tu base original. Si quieres revisar tus datos
locales, usa primero el respaldo de SQLite en modo de solo lectura explicado en
`REVISION_MIGRACIONES_FASE1.md`, creando `antes.sqlite3` y `ensayo.sqlite3` fuera
de Git. Detener previamente todos los escritores de la base de origen.

En una consola dedicada, configurar siempre la ruta de la copia explícitamente,
una clave nueva privada, desarrollo por HTTP local y correo en memoria:

```powershell
# Sustituir por LA COPIA independiente creada previamente, nunca por db.sqlite3.
$env:DJANGO_DB_PATH = 'C:\RUTA_PRIVADA\ensayo.sqlite3'
$env:DJANGO_SETTINGS_MODULE = 'config.settings'
$env:DJANGO_DEBUG = 'true'
$env:DJANGO_ALLOWED_HOSTS = '127.0.0.1,localhost'
$env:DJANGO_TIME_ZONE = 'America/Caracas'
$env:EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
if (-not $env:DJANGO_SECRET_KEY) {
    $env:DJANGO_SECRET_KEY = .\.venv-phase1\Scripts\python.exe -B -c "import secrets; print(secrets.token_urlsafe(64))"
}
.\.venv-phase1\Scripts\python.exe -B manage.py showmigrations --settings=config.settings
```

Si `LoginRegister.0003` y `0004` ya están aplicadas, **no apuntar hacia 0003**:
esa orden pediría una reversión. Revisar el plan general y avanzar solamente.

Si `LoginRegister.0003` está pendiente, seguir primero la secuencia del primer
administrador, siempre sobre la copia: aplicar solo 0003, crear/designar y
verificar al administrador mediante `bootstrap_admin`. Esa secuencia está
documentada en `REVISION_MIGRACIONES_FASE1.md`. No iniciar el navegador a mitad de
la actualización y no omitir la protección de 0004 con `--fake`.

Una vez preparado/verificado el administrador cuando corresponda:

```powershell
.\.venv-phase1\Scripts\python.exe -B manage.py migrate --plan --settings=config.settings
# Revisar el plan. Continuar solamente si coincide con las migraciones esperadas.
.\.venv-phase1\Scripts\python.exe -B manage.py migrate --settings=config.settings
if ($LASTEXITCODE -ne 0) { throw 'La migración falló. No iniciar el servidor ni tocar la base original.' }
.\.venv-phase1\Scripts\python.exe -B manage.py check --settings=config.settings
.\.venv-phase1\Scripts\python.exe -B manage.py runserver 127.0.0.1:8002 --noreload --settings=config.settings
```

No utilizar `config.test_settings` para este ensayo interactivo: fuerza memoria,
un hasher de pruebas y no abriría el archivo elegido. Las credenciales de la demo
no existen en la copia privada. Utilizar el administrador verificado para esa
copia, sin introducir ni modificar datos médicos reales durante las pruebas.

La comparación de datos del procedimiento de respaldo sigue siendo válida para
las columnas originales. Las columnas nuevas no deben utilizarse para inferir
información histórica. No copiar la demo ni el ensayo sobre `db.sqlite3` como
atajo. La aplicación al original sigue pendiente de autorización explícita.

## Pruebas y resultados

```powershell
.\.venv-phase1\Scripts\python.exe -B manage.py test --settings=config.test_settings --verbosity=2
.\.venv-phase1\Scripts\python.exe -B manage.py makemigrations --check --dry-run --settings=config.test_settings
.\.venv-phase1\Scripts\python.exe -B manage.py check --settings=config.test_settings
.\.venv-phase1\Scripts\python.exe -B scripts\verify_account_migrations_synthetic.py
.\.venv-phase1\Scripts\python.exe -B -m pip check
```

Las pruebas automatizadas usan SQLite y correo en memoria. El último script hace
además un ensayo con dos archivos físicos nuevos y datos ficticios desde los
esquemas 0002 de ambas aplicaciones. Conserva las bases de referencia/ensayo en
`.uptag-upgrade-...` para inspección y compara columnas originales, hashes,
relaciones, información clínica y las comprobaciones de integridad/clave foránea.
Comprueba que no haya categorías, médicos o llegadas inventados y verifica la
protección del primer administrador. No conecta a `db.sqlite3`; solo compara su
huella de archivo antes/después si existe.

Las pruebas cubren las categorías y externos sin campos institucionales,
duplicados equivalentes, búsqueda, cambio de categoría, auditoría personal,
registro independiente, llegadas, transiciones, cancelaciones, permisos por HTTP
y servicios, CSRF, consulta completa, corrección clínica con motivo, conflictos
de versión, rollback de auditorías e indicadores diarios sin contar cancelados.

La zona de presentación por defecto ahora es America/Caracas, configurable con
`DJANGO_TIME_ZONE`. Django conserva timestamps con zona horaria en almacenamiento;
no se reescriben fechas históricas. Los indicadores de finalización utilizan la
fecha de finalización y no la de llegada.

## Límites y pendientes

No se implementan aquí PDF institucionales, constancias de reposo, firmas,
antecedentes ni signos vitales. Las claves expuestas, la base y archivos ya
versionados mantienen los pendientes de seguridad de la entrega anterior; no se
reescribió el historial ni se eliminaron archivos. Deben resolverse antes de
publicar o desplegar. El motivo administrativo opcional no altera los eventos
históricos ni relaja la autorización clínica.


## Resultado final de esta revisión

| Verificación | Resultado |
| --- | --- |
| Pacientes y categorías | 12 pruebas aprobadas. |
| Llegadas, estados, consultas y correcciones | 19 pruebas aprobadas. |
| Autenticación, aprobación y administrador inicial | 40 pruebas aprobadas. |
| Suite completa con Django 5.2.18 | 87 pruebas aprobadas, cero fallos. |
| Compatibilidad con Django 5.2.7 del entorno original | Las mismas 87 pruebas aprobadas. |
| `makemigrations --check --dry-run` y comprobaciones de Django | Sin incidencias. |
| `pip check` | Sin incompatibilidades. |
| Ensayo físico desde los esquemas 0002 | Datos, relaciones, hashes e integridad conservados; sin clasificaciones ni responsables inventados. |
| SQLite original, archivo administrativo y logotipo frente a Git | Sin cambios de contenido. |
| Fuentes Python y `git diff --check` | Sin incidencias. |

La revisión visual se realizó con datos ficticios en 1366×900, 768×1024 y
390×844. Se verificaron menú móvil, campos condicionales, filtros, permisos
visibles y tabla desplazable. En móvil la página mantuvo su ancho; el contenido
ancho quedó dentro del contenedor desplazable de la tabla. Se corrigieron el
contraste del logotipo blanco, la anchura del filtro de fecha en tablet y el
formato ISO de la fecha precargada de consulta.

Evidencia con datos exclusivamente ficticios:

- [Atenciones en computadora](qa/atenciones-desktop.jpg).
- [Atenciones en móvil](qa/atenciones-mobile.jpg).

## Archivos principales de estas correcciones

- `Hisotria_clinica/models.py`, `forms.py`, `services.py`, `views.py`, `urls.py`.
- Migraciones clínicas `0003_patient_classification_audit.py`,
  `0004_attention_clinical_audit.py`, `0005_canonical_identity_key.py`.
- Plantillas clínicas `paciente.html`, `pacientes.html`, `expediente.html`,
  `nueva_consulta.html`, `atenciones.html`, `consulta_medica.html`, `correccion.html`,
  `detalle.html`. El formulario combinado anterior ya no se expone por rutas.
- `Hisotria_clinica/test_patients.py`, `test_workflow.py`, `test_migrations.py` y
  actualización de `test_access.py` y `tests.py`.
- `LoginRegister/forms.py`, `services.py`, `models.py`, `access.py`,
  `context_processors.py`, plantillas de cuentas y login, y pruebas correspondientes.
- `LoginRegister/migrations/0005_optional_administrative_reason.py`.
- `base/templates/base/header_navbar.html`, `base/static/base/css/styleheadernav.css`,
  `base/static/base/js/patient-form.js`, `navigation.js`.
- `dashboard/views.py`, plantilla del inicio y configuración horaria por entorno.
- `scripts/preview_medical_system.py`, ensayo físico actualizado, README,
  `.env.example`, `.gitignore`, documentación y capturas de QA.
