# Constancia de Reposo FOR-SSS-07

Actualización del 28/10/2026: consultar la [revisión integral](REVISION_INTEGRAL_FASE2.md).
La migración 0010 añade dos guardas contra reemplazos SQL a los dos triggers
originales: son cuatro protecciones en total. La suite vigente tiene 211 pruebas
aprobadas; las cifras inferiores de esta guía corresponden a la entrega anterior.
La revisión firmada también identifica la revisión de plantilla, y los datos PDF
usan DejaVu Sans con validación de glifos.

## Entrega y conservación

Implementado en `feature/uptag-medical-system-v2`, reutilizando consultas,
expedientes, autenticación, permisos, fuentes PDF y auditoría clínica existentes.
No se migró `db.sqlite3` original, eliminaron registros ni publicaron cambios.
Las pruebas usan memoria o archivos nuevos con información ficticia.

La constancia utiliza la hoja adjunta: A4 vertical, código FOR-SSS-07, logotipo
institucional ya incorporado, identificación de médico y paciente, duración,
motivo, fecha de emisión y línea de firma vacía. No se generan firmas ni sellos.
La aprobación queda registrada en el sistema; la firma o sello institucional
requiere su procedimiento autorizado. El pie se sitúa dentro del margen imprimible.

El texto identifica al paciente como estudiante, profesor(a), integrante del
personal obrero/técnico, integrante del personal administrativo o paciente externo.
No crea una categoría adicional para desvinculados. El PNF se incluye únicamente
para estudiantes y continúa siendo opcional. No se usa el cargo como dependencia
ni se inventan datos institucionales. La categoría Por verificar debe confirmarse
expresamente antes de preparar una constancia.

La fecha de emisión se toma del día de aprobación en America/Caracas. El período
se registra internamente con inicio y fin inclusivos; el final se calcula como
inicio + días - 1. La revisión muestra ambas fechas. El PDF conserva los campos
originales de duración y fecha de emisión, sin añadir campos ajenos a la hoja.

## Flujo de uso

1. Abrir la consulta ya completada y seleccionar Preparar constancia FOR-SSS-07.
   Paciente y médico se obtienen del sistema. Introducir motivo, días e inicio.
2. Guardar el borrador. Se registra autor, fecha, revisión y auditoría. Aún no
   existe PDF definitivo ni aprobación.
3. Revisar el paciente, médico, período, motivo y PDF marcado **BORRADOR - SIN
   APROBACIÓN**. Puede abrirse la vista previa en otra pestaña.
4. Marcar la confirmación explícita y pulsar Aprobar y guardar PDF definitivo.
5. Descargar, visualizar o imprimir la versión emitida. Se sirve el archivo
   guardado, sin regenerarlo desde la historia actual.
6. Para corregir, preparar una nueva versión desde la última emitida y justificar
   el motivo. Esta nueva versión requiere su propia revisión y aprobación. La
   anterior conserva todos sus datos, PDF, aprobador y fecha.

Solo se permite un borrador abierto por consulta y una cadena lineal de versiones.
Un borrador existente se consulta desde la lista de constancias de la consulta.
No se ofrecen botones de borrado. Un formulario repetido, revisión desactualizada
o aprobación duplicada se rechazan sin sobrescribir documentos.

## Autorización y revisión médica

La capacidad `manage_reposo` se limita a médicos activos y aprobados. Además,
preparar, editar, revisar y aprobar requiere ser el **médico responsable registrado
en esa consulta**. No se asigna un médico automáticamente a una historia antigua
ni se delega aprobación por ser administrador o superusuario técnico.

Otros médicos aprobados pueden consultar y descargar versiones ya emitidas del
expediente central. No pueden modificar, aprobar o acceder a borradores ajenos.
Enfermería y administración conservan la lectura clínica acordada en pantalla;
no tienen acciones de emisión, aprobación o descarga de reposos. Los controles
se aplican tanto en vistas como en servicios y consultas, no solo en enlaces.

La aprobación exige POST, CSRF, confirmación explícita, revisión vigente y número
de revisión actual del borrador. La vista previa produce un token firmado, ligado
al médico, borrador, revisión y huella de los datos a imprimir. Caduca a los 30 minutos.
Cambiar el borrador, una versión clínica, datos impresos del paciente/médico o el
día de emisión obliga a revisar de nuevo. La firma del token no contiene nombres
ni información clínica: contiene identificadores y una huella, y se envía en el
formulario protegido, no en la URL.

La consulta requiere médico responsable, motivo, diagnóstico y tratamiento. Si
tiene atención relacionada, debe estar Atendido y corresponder al paciente. Las
fechas deben ser coherentes con el nacimiento y no tener consulta futura. Nombres,
apellidos, cédula y categoría deben estar confirmados. No se exige haber completado
los campos exclusivos del FOR-SSS-04 para este formato distinto.

El motivo del reposo es un dato clínico independiente. No se copia automáticamente
el diagnóstico en el espacio que se entrega al paciente. Se conserva el texto
redactado por el médico, con acentos y caracteres escapados de forma segura.

La hoja admite cinco líneas de motivo con ajuste al ancho. Textos, nombres o PNF
que no caben bloquean la vista previa/emisión con un mensaje; no se truncan, resumen
ni reducen fuentes automáticamente. Los datos no se modifican para ajustar el PDF.

## Versiones inmutables y auditoría

Nuevo modelo **ConstanciaReposo**, ligado mediante PROTECT a la historia, usuarios
y versión anterior. Contiene motivo, período, número de versión, estado, autor,
revisión optimista y, tras aprobar, responsable/fecha de aprobación, copia fija de
los datos utilizados, PDF binario y SHA-256.

El PDF se almacena dentro de SQLite para guardar documento, aprobación y auditoría
en una sola transacción. Un fallo de auditoría o generación revierte la operación.
No hay archivos clínicos en directorios públicos ni ventanas de fallo entre escritura
de un archivo y confirmación de la base. Los listados no cargan los PDF completos.

La protección incluye:

- Servicio que rechaza cambios o reemisiones de una fila ya emitida.
- Modelo que impide guardar otra vez una versión emitida y no ofrece borrado ordinario.
- Triggers SQLite que bloquean UPDATE y DELETE de filas emitidas, incluso mediante
  QuerySet o SQL directo ordinario.
- Restricciones de versión única, un borrador abierto, días positivos, período
  coherente y emisión con PDF, huella, datos y aprobador completos.
- Verificación SHA-256 al descargar. Una huella discordante produce un error;
  no se reemplaza silenciosamente el archivo por otro generado desde datos actuales.

La inmutabilidad se aplica dentro de la aplicación y sus restricciones de SQLite.
No equivale a una firma criptográfica del médico ni protege frente a una persona
con acceso administrativo al archivo que retire deliberadamente las protecciones.
Los respaldos y el control de acceso al archivo de base siguen siendo necesarios.

Se reutiliza AuditoriaClinica para registrar preparación, modificación del borrador,
aprobación y creación de versiones. Conserva responsable, fecha y valores anteriores/
nuevos, número de versión y huella de la emisión. Editar un borrador guardado requiere
motivo; una corrección mediante nueva versión también exige su justificación.
Los eventos anteriores de auditoría y la información clínica previa no se reescriben.

La descarga de una versión no modifica datos ni auditorías y no consulta fuentes
actuales para reconstruir su PDF. Cambiar nombres, categoría, diagnóstico o incluso
el estado posterior de la ficha no altera las versiones emitidas.

## Migración y almacenamiento

**`Hisotria_clinica.0009_rest_certificates`** depende de 0008. Crea la tabla,
índices, restricciones y dos triggers de protección; no incorpora reposos ficticios
a consultas históricas ni modifica tablas/columnas anteriores. Los triggers están
implementados para SQLite, el motor del proyecto.

No revertir esta migración como procedimiento de recuperación: eliminar la tabla
destruiría documentos nuevos. Respaldar el archivo SQLite completo, que ahora
contiene también los PDF y sus datos de emisión. El tamaño de la base crecerá
con cada documento aprobado. Conservar respaldos privados fuera de Git y probar
la restauración sobre copias. Las futuras migraciones que reconstruyan esta tabla
deben conservar o reinstalar los triggers; un cambio de motor debe adaptar esas
protecciones y volver a ejecutar sus pruebas.

La aplicación al original sigue sin autorización. Para un ensayo, crear primero
una copia privada mediante el procedimiento SQLite de solo lectura de
[Revisión de migraciones](REVISION_MIGRACIONES_FASE1.md), preparar el administrador
si cuentas 0003/0004 siguen pendientes y configurar las variables de entorno de
[la guía de pacientes](CORRECCIONES_PACIENTES_ATENCION.md).

Con `DJANGO_DB_PATH` apuntando expresamente a la copia, revisar showmigrations y
migrate --plan antes de avanzar. Aplicar migrate solo en esa copia y ejecutar check.
No usar --fake ni retroceder a una migración anterior ya aplicada. No copiar una
demo sobre el original. Estas acciones sobre una copia son instrucciones; no se
ejecutaron sobre la base original durante esta entrega.

## Probar en PowerShell sin usar datos reales

Desde la carpeta del repositorio:

```powershell
.\.venv-phase1\Scripts\python.exe -B -m pip install -r requirements-dev.txt
.\.venv-phase1\Scripts\python.exe -B scripts\preview_medical_system.py --port 8005
```

El script crea otra SQLite ficticia `.uptag-demo-...` y muestra credenciales
aleatorias. No consume `DJANGO_DB_PATH` heredada ni abre el SQLite original.
Abrir `http://127.0.0.1:8005/` e ingresar como médico. En Pacientes e historias,
abrir una consulta: una tiene borrador y otra una muestra aprobada. Desde sus
constancias se puede revisar, aprobar, descargar y preparar una versión nueva.
Enfermería y administración sirven para comprobar las restricciones.

Cada ejecución crea otra demo; no migra ni sobrescribe demostraciones antiguas.
Usar un puerto libre y la URL impresa. No reutilizar un servidor antiguo, porque
la demo se inicia sin recarga automática. Ctrl+C detiene el servidor sin borrar datos.

Para generar solo la muestra con una base exclusivamente en memoria:

```powershell
.\.venv-phase1\Scripts\python.exe -B scripts\preview_reposo_pdf.py
```

Prepara, revisa y aprueba una constancia ficticia mediante los servicios reales;
extrae su PDF guardado a `output/pdf/FOR-SSS-07_demo.pdf`. La salida y renders están
excluidos de Git. No introduce datos reales ni aplica migraciones al original.
Para impresión, seleccionar A4 vertical a tamaño real; el visor ofrece su botón
nativo y la página también dispone de Imprimir PDF. No se envió una impresión física.

## Pruebas y archivos

```powershell
.\.venv-phase1\Scripts\python.exe -B manage.py test --settings=config.test_settings --verbosity=1
.\.venv-phase1\Scripts\python.exe -B manage.py makemigrations --check --dry-run --settings=config.test_settings
.\.venv-phase1\Scripts\python.exe -B scripts\verify_account_migrations_synthetic.py
.\.venv-phase1\Scripts\python.exe -B -m pip check
```

**197 pruebas aprobadas con Django 5.2.18**, incluidas 35 de reposos y una nueva
de conservación 0008→0009. Cubren permisos por rol/objeto/HTTP, revocación de cuentas,
CSRF, revisión firmada/expirada, cambios después de revisar, concurrencia optimista,
aprobación repetida, períodos inclusivos/bisiestos, categorías, PNF opcional,
auditoría y rollback, cadena de versiones, SQL/ORM inmutables, documentos guardados
tras correcciones de fuente, hash, contenido literal, límites de cinco líneas,
errores y vista previa/descarga/impresión. Las pruebas anteriores de ambos PDF
y todos los módulos permanecen aprobadas.

El ensayo físico conserva usuarios, hashes y relaciones históricas ficticias.
La prueba de migración compara columnas anteriores y auditorías, comprueba que no
se creen constancias históricas y verifica integrity_check, foreign_key_check y
presencia de ambos triggers. Django, makemigrations, pip check y diff sin incidencias.
Se renderizó y revisó la muestra a 120 dpi, incluidos logotipo, encabezado, campos,
líneas, acentos, márgenes y ausencia de firmas simuladas.

Archivos principales:

- `Hisotria_clinica/models.py` y `migrations/0009_rest_certificates.py`.
- `Hisotria_clinica/reposos.py`, `pdf_reposos.py`, `forms_reposos.py`, `views_reposos.py`.
- `Hisotria_clinica/urls.py`, integración de constancias en `views.py` y detalle de historia.
- `templates/historia/reposos/`, permisos/contexto de LoginRegister.
- `Hisotria_clinica/test_reposos.py`, `test_migrations.py`.
- `scripts/preview_reposo_pdf.py`, demo general y documentación.
