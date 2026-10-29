# Ocho opciones clínicas y PDF FOR-SSS-02

La ampliación posterior de [Historia Clínica FOR-SSS-04](FASE2_HISTORIA_PDF.md)
añade la migración 0008 y eleva la suite a 161 pruebas. Los resultados y pendientes
descritos abajo corresponden a la entrega previa del diario.

## Alcance

Implementado en `feature/uptag-medical-system-v2`. Se conservan las funciones
anteriores, las cinco categorías, el indicador histórico Por verificar y las
auditorías. No se migró ni modificó `db.sqlite3` original. No hay publicación,
push ni Pull Request. Este paso implementa el PDF diario; no incluye todavía los
documentos FOR-SSS-04 y FOR-SSS-07.

En crear/corregir consulta aparecen dos grupos independientes y opcionales:

| Grupo | Etiqueta literal | Código de almacenamiento |
| --- | --- | --- |
| Datos adicionales del Registro Médico Diario | RP | `rp` |
| Datos adicionales del Registro Médico Diario | T de C | `t_de_c` |
| Estudios y procedimientos solicitados | Tto | `tto` |
| Estudios y procedimientos solicitados | Lab | `lab` |
| Estudios y procedimientos solicitados | Ref | `ref` |
| Estudios y procedimientos solicitados | Imag | `imag` |
| Estudios y procedimientos solicitados | Rx | `rx` |
| Estudios y procedimientos solicitados | Cit | `cit` |

No se desarrollan las abreviaturas ni se infieren indicaciones desde diagnóstico,
tratamiento, motivo u otro texto. El campo de texto tratamiento no activa Tto.
Los códigos y nombres de columnas del modelo son estables aunque posteriormente
se autoricen etiquetas descriptivas diferentes.

## Datos y permisos

La migración **`Hisotria_clinica.0007_daily_register_options`** agrega ocho
BooleanField nullable al modelo existente HistoriaClinica. No crea otra tabla de
consultas, cambia identificadores ni rellena selecciones históricas. Las consultas
anteriores quedan en NULL, presentado como Sin información registrada; una consulta
nueva creada mediante el servicio guarda False para las casillas sin marcar.

Una corrección parcial por servicio conserva los demás NULL. Guardar el formulario
completo de corrección registra el estado explícito de sus ocho casillas. Requiere
motivo y conserva anteriores/nuevos, médico, fecha y versión. El servicio solo
acepta booleanos reales para selecciones nuevas: rechaza textos, enteros y NULL.
Las operaciones y auditorías son transaccionales; un error revierte ambos cambios.

Solo los médicos activos, aprobados y autorizados crean o cambian estas selecciones.
Enfermería y administración las consultan en lectura. Los permisos se comprueban
en vistas y servicios; las banderas técnicas de superusuario no conceden escritura.
La auditoría y el control optimista de versiones anteriores siguen vigentes.

No se deben revertir migraciones como forma de recuperación: al quitar las nuevas
columnas se perderían las selecciones guardadas después de su aplicación.

## PDF, vista previa e impresión

Desde Registro Médico Diario se ofrecen Visualizar PDF, Descargar PDF e Imprimir.
Los filtros de fecha/rango conservan extremos inclusivos y máximo 366 días.
Se reutiliza el mismo reporte autorizado: fecha de finalización en America/Caracas,
grupos por médico/enfermera/turno y solo atenciones finalizadas verificables.
Cada fecha y equipo inicia una planilla; más de 17 consultas generan otra página.
Cada página conserva 17 filas, encabezado, código FOR-SSS-02 y total de esa página.
Una fecha sin resultados también tiene su planilla vacía, sin inventar equipo.

La distribución de columnas y dimensiones reproduce la referencia suministrada:
A4 horizontal, aproximadamente 842×595 puntos. RP se marca en Rp y T de C en T.C.;
no se deduce P/S. Las otras seis casillas se marcan en sus columnas literales.
Se dibuja X solamente cuando el valor guardado es True. False y NULL dejan la
celda vacía; NULL significa ausencia de información, no selección negativa verificada.

El logotipo a color adjunto se conserva como activo documental separado en
`base/static/base/img/logo_uptag_documentos.png`. El logotipo de la aplicación
permanece intacto. Se sustituyó el marcador ESCUDO de la referencia; las notas
técnicas de transcripción no forman parte del documento emitido.

Los datos sin fuente registrada permanecen vacíos: en particular C.I. del médico
y especialidad, que no existen todavía en los modelos. No hay edición libre de
esos valores al descargar ni inferencias desde otros campos.

El texto es seleccionable y utiliza fuentes TrueType incluidas con ReportLab.
Se comprueba el espacio disponible antes de terminar el PDF. Si una celda o un
encabezado no admite el texto, se bloquea la emisión (HTTP 422) con una explicación;
no se recorta, resume ni modifica la historia para ajustarla. Las inconsistencias
de atenciones advertidas en el diario también bloquean la emisión del rango.
Las consultas históricas sin atención trazable siguen fuera del diario según la
decisión anterior, consultables en el expediente y en las advertencias web.

Los documentos se generan en memoria a petición, con autenticación actual,
no-store y sin rutas públicas de archivos. La descarga usa Content-Disposition
attachment y la vista previa inline. Solo el endpoint PDF permite iframe del mismo
origen para imprimir. El visor del navegador también ofrece sus controles nativos;
si el botón de la página no abre el diálogo, usar el del visor o abrir otra pestaña.
Elegir A4 horizontal a tamaño real. La impresión física depende del navegador e impresora.

Este reporte refleja datos vigentes y sus correcciones auditadas. No es una
constancia inmutable; el almacenamiento/versionado de reposos es otro alcance.

## Dependencias y demostración segura

En PowerShell, desde la carpeta del proyecto:

```powershell
.\.venv-phase1\Scripts\python.exe -B -m pip install -r requirements-dev.txt
.\.venv-phase1\Scripts\python.exe -B scripts\preview_medical_system.py --port 8003
```

`requirements.txt` incorpora ReportLab 4.4.9, Pillow 13.0.0 y charset-normalizer
3.5.2. `requirements-dev.txt` agrega pypdf 6.10.0 para verificar el contenido y las
coordenadas del PDF. No se requiere Poppler en el servidor; se usó para inspección
visual durante QA.

El segundo comando crea otra SQLite ficticia `.uptag-demo-...`, ignora rutas de
bases heredadas y muestra credenciales aleatorias. No reutilizar un servidor antiguo
para verificar código nuevo: cada demo se inicia sin recarga automática.
Abrir la URL indicada y entrar con el médico o la enfermera. El médico puede
corregir con motivo las casillas de las consultas ficticias y consultar el diario.

Para producir una muestra PDF sin servidor ni SQLite de archivo:

```powershell
.\.venv-phase1\Scripts\python.exe -B scripts\preview_daily_pdf.py
```

Usa exclusivamente SQLite en memoria y genera `output/pdf/FOR-SSS-02_demo.pdf`:
fecha vacía más 18 consultas ficticias, en tres páginas. Los PDF generados y
renders temporales se excluyen de Git para prevenir publicación accidental de
documentos médicos. No introducir datos reales en estas demostraciones.

## Aplicación sobre una copia independiente

La base original sigue sin autorización para migrar. Seguir el respaldo SQLite
de solo lectura y la preparación del administrador de
[la revisión de migraciones](REVISION_MIGRACIONES_FASE1.md). Configurar explícitamente
`DJANGO_DB_PATH` con la ruta de una copia de ensayo, una clave privada nueva y las
variables de desarrollo descritas en [la guía de pacientes](CORRECCIONES_PACIENTES_ATENCION.md).

Si cuentas 0003/0004 aún están pendientes, cumplir primero su secuencia de
administrador inicial. No retroceder a una migración anterior ya aplicada y no
utilizar --fake. Con la copia preparada:

```powershell
.\.venv-phase1\Scripts\python.exe -B manage.py showmigrations --settings=config.settings
.\.venv-phase1\Scripts\python.exe -B manage.py migrate --plan --settings=config.settings
# Revisar la ruta a la COPIA y el plan antes de continuar.
.\.venv-phase1\Scripts\python.exe -B manage.py migrate --settings=config.settings
if ($LASTEXITCODE -ne 0) { throw 'Migración fallida; no iniciar el servidor.' }
.\.venv-phase1\Scripts\python.exe -B manage.py check --settings=config.settings
.\.venv-phase1\Scripts\python.exe -B manage.py runserver 127.0.0.1:8003 --noreload --settings=config.settings
```

No utilizar test_settings para abrir una copia en el navegador: siempre selecciona
SQLite en memoria. No copiar ninguna demo ni ensayo sobre el original.

## Verificación

```powershell
.\.venv-phase1\Scripts\python.exe -B manage.py test --settings=config.test_settings --verbosity=1
.\.venv-phase1\Scripts\python.exe -B manage.py makemigrations --check --dry-run --settings=config.test_settings
.\.venv-phase1\Scripts\python.exe -B scripts\verify_account_migrations_synthetic.py
.\.venv-phase1\Scripts\python.exe -B -m pip check
```

La suite completa contiene **136 pruebas aprobadas** con Django 5.2.18, incluyendo
21 nuevas de opciones/PDF y una nueva de migración 0006→0007. Comprueban selección
independiente/múltiple/vacía, creación y desmarcado por HTTP, etiquetas/códigos,
NULL históricos, permisos, motivo, versiones, rollback y lectura sin escrituras.
Los PDF se verifican por texto y coordenadas: ocho X en sus columnas, celdas no
seleccionadas vacías, datos automáticos, logo, A4, 17 filas en cada página, límites
17/18/34/35, rangos, días vacíos, equipos, errores y acceso protegido.

La prueba de migración compara todas las columnas anteriores de paciente, historia,
auditoría y usuario, incluyendo hashes y relaciones; ejecuta integrity_check y
foreign_key_check. No rellena casillas a partir del tratamiento histórico.
Se renderizaron y revisaron las tres páginas ficticias a 120 dpi.

En navegador se comprobaron los dos grupos, las ocho casillas precargadas, las
marcas del diario y el acceso al visor. Se verificó el ancho del formulario en
computadora y móvil mediante DOM; la captura de pantalla del navegador no estuvo
disponible en esta sesión. El visor y su PDF respondieron HTTP 200 con la demo
corregida. No se envió ningún trabajo a una impresora física.

Durante QA se detectó que las categorías usadas como apellidos en la demo anterior
desbordaban el espacio de nombre. Se acortaron exclusivamente esos datos ficticios
en nuevas demostraciones. La validación de impresión también se adelantó para no
ofrecer controles alrededor de un error de generación dentro del iframe.

## Archivos principales

- `Hisotria_clinica/daily_options.py`, `models.py`, `forms.py`, `services.py`.
- `Hisotria_clinica/migrations/0007_daily_register_options.py`.
- `Hisotria_clinica/reports.py`, `pdf_reports.py`, `views.py`, `urls.py`.
- Plantillas `clinical_fields.html`, `consulta_medica.html`, `correccion.html`,
  `detalle.html`, `reportes/diario.html`, `reportes/imprimir.html`.
- `base/static/base/css/styleheadernav.css`, `base/static/base/js/print-daily.js`,
  activo documental del logo.
- `Hisotria_clinica/test_daily_options.py`, `test_migrations.py`.
- Scripts de vista previa, dependencias, exclusiones Git y documentación.
