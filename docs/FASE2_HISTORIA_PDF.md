# Historia Clínica FOR-SSS-04: una hoja por consulta

La entrega posterior de [Constancia de Reposo FOR-SSS-07](FASE2_REPOSO_PDF.md)
incorpora la migración 0009 y eleva la suite a 197 pruebas. Los pendientes de reposos
descritos en esta guía corresponden a la entrega anterior de historia clínica.

## Alcance y conservación

Implementación sobre `feature/uptag-medical-system-v2`. Se conserva el proyecto
Django existente, su autenticación, expedientes, consultas, ocho casillas del diario,
cinco categorías, estados y auditorías. No se migró ni modificó `db.sqlite3`
original ni se publicaron cambios. La Constancia de Reposo FOR-SSS-07 continúa
fuera de este paso.

El PDF reproduce exclusivamente la hoja suministrada: A4 vertical, código
FOR-SSS-04, logotipo institucional a color ya incorporado, datos personales y tres
secciones: Motivo de la consulta, Enfermedad actual y Diagnóstico provisional.
Mantiene las líneas y distribución de la referencia. No incorpora tratamiento,
diagnóstico general, observaciones, casillas del diario, firmas ni secciones ajenas
a esa hoja. El marcador ESCUDO y la nota técnica de transcripción no se imprimen.

Es un documento independiente por consulta, con texto seleccionable y fuente
TrueType. Se reutilizan ReportLab y los validadores de espacio del diario;
no hay dependencias nuevas. No se reducen automáticamente fuentes, recortan textos,
resumen notas ni añaden páginas o anexos. Si el contenido excede el espacio,
se rechaza la emisión con HTTP 422 y una explicación; la historia no se modifica.
Las secciones admiten hasta tres, cinco y tres líneas, respectivamente, con ajuste
automático al ancho disponible. Un salto de línea explícito también ocupa una línea.

## Campos añadidos y auditoría

Migración **`Hisotria_clinica.0008_clinical_history_document_fields`**, posterior a
0007. Añade únicamente campos con blanco permitido y valor inicial vacío:

| Modelo existente | Campo | Uso |
| --- | --- | --- |
| `Estudiante` | `lugar_nacimiento` | Lugar junto a la fecha de nacimiento existente. |
| `Estudiante` | `parentesco_emergencia` | Parentesco del contacto de emergencia. |
| `Estudiante` | `telefono_emergencia` | Teléfono propio del contacto, separado del paciente. |
| `HistoriaClinica` | `enfermedad_actual` | Información clínica propia de esa consulta. |
| `HistoriaClinica` | `diagnostico_provisional` | Información clínica propia de esa consulta. |

No renombra modelos/tablas, reemplaza valores, cambia identificadores ni crea
consultas nuevas para completar el pasado. Las columnas anteriores, relaciones,
cuentas, contraseñas, casillas y auditorías se conservan. No copia diagnóstico a
provisional, observaciones a enfermedad actual ni teléfono del paciente al contacto.
No clasifica automáticamente los pacientes por verificar.

Los tres datos personales nuevos aparecen en el formulario y expediente; siguen
siendo opcionales. Enfermería y médicos pueden registrarlos o corregirlos con los
servicios existentes; administración conserva lectura. La auditoría personal
incluye anteriores/nuevos, usuario y fecha.

Los dos campos clínicos aparecen en crear consulta, corregir y consultar historia.
Solo médicos activos, aprobados y autorizados pueden escribirlos. Toda corrección
clínica exige motivo y versión vigente, conservando anteriores/nuevos, responsable
y fecha en la auditoría existente, de forma transaccional. Un error de auditoría
revierte la modificación. La autenticación, CSRF y restricciones de enfermería
y administración se conservan también ante peticiones directas.

Para compatibilidad, el registro ordinario de una consulta conserva sus requisitos
previos. Los campos nuevos pueden permanecer vacíos, pero una consulta incompleta
para el formato **no permite emitir su PDF**. Completarlos posteriormente requiere
la corrección médica auditada. No se sustituyó el flujo ni se añadió un estado ficticio.

## Permisos y validación de emisión

La capacidad `export_clinical` corresponde exclusivamente a médicos activos y
aprobados. Se comprueba en las vistas y en el servicio, consultando la cuenta actual.
Enfermería y administración pueden leer los campos en pantalla, sin acciones de
emisión PDF. Ser superusuario técnico no concede permiso médico.

En la consulta, el médico dispone de Visualizar FOR-SSS-04, Descargar PDF e Imprimir.
Las rutas utilizan el identificador de consulta, no un identificador de paciente:

```text
/historia/consulta/<id>/pdf/
/historia/consulta/<id>/pdf/?download=1
/historia/consulta/<id>/imprimir/
```

El servicio reutiliza la consulta y el expediente central autorizados; no acepta
datos clínicos alternativos por parámetros de URL ni rutas de archivos. Exige:

- Nombres, apellidos, cédula, fecha de nacimiento, sexo, estado civil, dirección,
  teléfono y contacto de emergencia registrados.
- Fecha y médico responsable de la consulta, motivo, enfermedad actual y diagnóstico
  provisional. También debe conservar el diagnóstico general y tratamiento que el
  flujo existente exige para una consulta completa, aunque no se impriman en esta hoja.
- Fechas coherentes: nacimiento no posterior a consulta y consulta no futura,
  evaluada en America/Caracas.
- Si existe una atención vinculada, debe corresponder al mismo paciente y estar Atendido.
- Espacio suficiente para cada dato y sección, sin truncamiento.

El lugar de nacimiento, parentesco, teléfono de emergencia y PNF siguen siendo
opcionales: su ausencia se imprime en blanco. Se incluye PNF solo si la categoría
actual es Estudiante; no se exige a externos o trabajadores ni se usa el cargo en
su lugar. La edad se calcula al día de la consulta desde el nacimiento, sin utilizar
la edad histórica almacenada ni la edad actual del paciente.

Las historias antiguas con nuevos campos vacíos no se emiten hasta su revisión
médica explícita. La falta de médico original registrado tampoco se sustituye por
el usuario que descarga. No se asigna automáticamente médico ni atención histórica.

El PDF usa los datos personales vigentes del expediente y los datos clínicos de esa
consulta, con sus auditorías. No es una instantánea inmutable; el versionado de
constancias definitivas pertenece al módulo de reposo pendiente.

La generación es de solo lectura, en memoria, sin guardar archivos clínicos públicos
ni modificar versiones o auditorías. Responde application/pdf, inline o attachment,
con no-store. Solo el PDF permite iframe del mismo origen para la pantalla de impresión.
Las rutas admiten GET/HEAD; POST no modifica ni emite. La vista de impresión valida
antes de ofrecer los controles. Seleccionar A4 vertical a tamaño real; también puede
usarse el botón nativo del visor. No se envió ninguna impresión física durante QA.

## Demostración y visualización segura

En PowerShell, desde el repositorio:

```powershell
.\.venv-phase1\Scripts\python.exe -B -m pip install -r requirements-dev.txt
.\.venv-phase1\Scripts\python.exe -B scripts\preview_medical_system.py --port 8004
```

Cada ejecución crea otra SQLite ficticia `.uptag-demo-...` e ignora rutas de base
heredadas. Aplica migraciones solo en esa base vacía. Muestra credenciales aleatorias
para los tres roles. Abrir `http://127.0.0.1:8004/`, entrar como médico, abrir
Pacientes e historias, seleccionar un expediente y su consulta. Desde allí se puede
visualizar, descargar o imprimir FOR-SSS-04 y corregir con motivo.

La demo incluye los campos nuevos completos en sus consultas ficticias. Si un puerto
está ocupado, elegir otro. No reutilizar un servidor anterior: las demos se ejecutan
sin recarga automática y las antiguas SQLite no se migran al iniciar otra demo.
No introducir información real. Ctrl+C detiene el servidor sin borrar la demo.

Para producir únicamente la muestra PDF, sin servidor ni SQLite de archivo:

```powershell
.\.venv-phase1\Scripts\python.exe -B scripts\preview_history_pdf.py
```

Fuerza SQLite en memoria y crea `output/pdf/FOR-SSS-04_demo.pdf`, de una sola hoja,
con datos ficticios. El directorio de salida y los renders temporales están excluidos
de Git. El archivo no procede de la base original.

## Ensayo de migraciones y pruebas

La aplicación al original sigue sin autorización. Para una copia independiente,
seguir el respaldo SQLite de solo lectura y la secuencia segura del primer
administrador de [la revisión de migraciones](REVISION_MIGRACIONES_FASE1.md).
Configurar `DJANGO_DB_PATH` explícitamente a la copia privada de ensayo y las
variables de entorno de [la guía de pacientes](CORRECCIONES_PACIENTES_ATENCION.md).
Si cuentas 0003/0004 están pendientes, completar primero esa preparación.
No retroceder a migraciones ya aplicadas ni usar --fake.

Con copia y administrador preparados, revisar showmigrations y migrate --plan antes
de avanzar. Aplicar migrate únicamente a la copia y ejecutar check antes de abrir
el servidor. No usar test_settings para un ensayo interactivo con archivos: fuerza
memoria y no abriría la copia elegida. No reemplazar el original por una demo o ensayo.

```powershell
.\.venv-phase1\Scripts\python.exe -B manage.py test --settings=config.test_settings --verbosity=1
.\.venv-phase1\Scripts\python.exe -B manage.py makemigrations --check --dry-run --settings=config.test_settings
.\.venv-phase1\Scripts\python.exe -B scripts\verify_account_migrations_synthetic.py
.\.venv-phase1\Scripts\python.exe -B -m pip check
```

Resultado: **161 pruebas aprobadas con Django 5.2.18**, incluyendo 24 nuevas de
campos/PDF y una de conservación 0007→0008. Comprueban consultas independientes,
campos automáticos, edad histórica, categorías/PNF, opciones previas, permisos por
HTTP/servicio, CSRF, auditoría, motivo, versiones, rollback, rangos de fechas
coherentes, datos incompletos, contenido literal escapado y bloqueo de desbordamientos.
Se comprueba la capacidad exacta de tres/cinco/tres líneas y se rechaza una adicional.

La prueba de migración compara todas las columnas anteriores de pacientes,
historias, atenciones, auditorías personales/clínicas, estados y usuarios, con
claves foráneas e integrity_check válidos. El ensayo físico sintético conserva
cuentas, hashes, relaciones y datos previos. La suite anterior, incluido el diario
PDF, permanece aprobada. Django, makemigrations, pip check y git diff --check sin errores.

Se renderizó la muestra a 120 dpi y se revisaron distribución, líneas, acentos,
legibilidad, márgenes y ausencia de secciones o páginas adicionales.

## Archivos principales

- `Hisotria_clinica/models.py`, `forms.py`, `services.py` y migración 0008.
- `Hisotria_clinica/pdf_histories.py`; reutilización de fuentes/validación desde
  `pdf_reports.py` con tamaño de página y espaciado configurables.
- `Hisotria_clinica/views.py`, `urls.py`, plantillas de detalle/expediente y
  `templates/historia/documentos/` para impresión y errores.
- `LoginRegister/access.py`, `context_processors.py`.
- `Hisotria_clinica/test_history_pdf.py`, `test_migrations.py`.
- `scripts/preview_history_pdf.py`, actualización de la demo general y documentación.
