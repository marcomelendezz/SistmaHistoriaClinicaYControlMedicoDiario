# Revisión integral de Fase 2 — 28/10/2026

Trabajo en `feature/uptag-medical-system-v2`. Se conservaron las ampliaciones anteriores.
No se aplicaron migraciones al SQLite original, no se borraron registros y no se
publicaron cambios. Los ensayos usaron bases nuevas ficticias o SQLite en memoria.

## Fallos reproducidos y corregidos

1. **Reposos emitidos reemplazables mediante SQL REPLACE.** Los triggers anteriores
   impedían UPDATE y DELETE ordinarios, pero SQLite puede borrar la fila que entra
   en conflicto con REPLACE sin ejecutar sus triggers DELETE cuando no está habilitada
   la recursividad. Se reprodujo el fallo con la configuración SQLite real. La nueva
   migración `Hisotria_clinica.0010_protect_issued_replacements` añade dos guardas
   BEFORE INSERT/UPDATE: protegen identificador, versión única por historia y enlace
   único a la versión anterior. No depende de `recursive_triggers`. Mantiene las dos
   protecciones anteriores y permite crear versiones nuevas válidas. Véase el
   [comportamiento documentado por SQLite](https://www.sqlite.org/lang_conflict.html).
2. **Pérdida silenciosa de caracteres en PDF.** La fuente anterior no representaba
   algunos símbolos; `β` y `CO₂` se perdían al extraer texto. Los tres documentos usan
   ahora DejaVu Sans 2.37 para los datos. La fuente y su licencia están incorporadas;
   no se añadió una dependencia Python. Un carácter sin glifo se rechaza con un
   mensaje y código Unicode antes de emitir, en lugar de sustituirse silenciosamente.
   Los títulos conservan la fuente en negrita existente. Véase la
   [licencia de DejaVu](https://dejavu-fonts.github.io/License.html).
3. **Finalización clínica con campos en blanco o fechas inválidas desde servicios.**
   Se exige contenido real en motivo, diagnóstico y tratamiento, además de fecha
   entre nacimiento y hoy en Caracas. Un rechazo no finaliza la atención, no crea
   una historia parcial ni deja auditoría de una modificación inexistente.
   Las correcciones exigen motivo y versión vigente. Una fecha histórica inválida
   no se modifica automáticamente al corregir otro campo; bloquea el documento
   definitivo hasta su corrección explícita y auditada.
4. **Revisión previa de reposo sin identificar la revisión de plantilla.** La huella
   de revisión incluye ahora la revisión de plantilla. Si cambia, hay que revisar
   otra vez antes de aprobar. Los PDF emitidos anteriormente siguen sirviéndose
   desde sus bytes guardados y no se regeneran. Una modificación futura de la
   plantilla o sus fuentes debe actualizar `TEMPLATE_REVISION`.
5. **Demostración susceptible a una zona horaria heredada.** La demo y los tres
   generadores de muestras fijan `America/Caracas`. Se ensayó la preparación con
   `Pacific/Kiritimati` heredada: creó correctamente otra base y utilizó Caracas.

## Permisos y conservación verificados

| Operación | Médico aprobado | Enfermera aprobada | Administrador aprobado |
| --- | --- | --- | --- |
| Registrar llegada / iniciar atención | Sí | Sí | No |
| Redactar o corregir información clínica | Sí, con auditoría | No | No |
| Consultar historias en pantalla | Sí | Sí | Sí, lectura |
| Diario, pendientes y PDF FOR-SSS-02 | Sí | Sí | No |
| PDF FOR-SSS-04 | Sí | No | No |
| Preparar, revisar y aprobar reposo | Solo médico responsable de esa consulta | No | No |
| Leer PDF de reposo ya emitido | Sí | No | No |

Las verificaciones se ejecutan en servidor y servicios. Un superusuario técnico
no adquiere permisos médicos. Cuentas pendientes o desactivadas quedan bloqueadas,
incluso con una sesión previamente autenticada. Otro médico aprobado puede consultar
un reposo emitido, pero no acceder al borrador ajeno ni aprobarlo.

Se mantienen las cinco categorías y el indicador histórico Por verificar, los
identificadores, relaciones, contraseñas y auditorías anteriores. Una constancia
emitida conserva copia de datos, PDF, SHA-256, aprobador y fecha. Cada corrección
crea otra versión vinculada, con motivo obligatorio, revisión y aprobación propias.
Los cambios de fuente posteriores no alteran los bytes de las versiones emitidas.

## Resultados comprobados

- **211 pruebas automatizadas aprobadas** con Django 5.2.18: las 197 anteriores y
  14 regresiones nuevas. Incluyen los tres PDF, roles, revocaciones, permisos por
  objeto, CSRF, auditoría transaccional, correcciones, concurrencia, revisión
  expirada/desactualizada, versiones, BLOB guardado, hash y reemplazos SQL.
- Migración 0009 → 0010 ensayada con un reposo ficticio ya emitido: usuarios,
  hashes, columnas, copia de datos de esquema anterior, PDF y auditoría idénticos;
  cuatro triggers presentes, integridad SQLite y claves foráneas correctas.
- Ensayo de actualización histórica independiente: ocho cuentas ficticias,
  contraseñas, relaciones, grupos, permisos, pacientes e historias conservados;
  administrador inicial y acceso al panel comprobados. La 0004 sigue bloqueándose
  si no hay administrador previamente verificado.
- `check`: sin problemas. `makemigrations --check --dry-run`: sin cambios pendientes
  de generar. `pip check`: sin dependencias incompatibles.
- Se renderizaron e inspeccionaron las cinco páginas de muestra: diario con fecha
  vacía y 18 pacientes repartidos en dos páginas, historia y reposo de una página.
  No se observaron cortes, solapamientos ni marcas fuera de sus columnas.
- Navegador contra otra demo nueva: diario con dos equipos, descarga real de PDF,
  corrección clínica con motivo y aprobación de reposos v1/v2. La huella de v1
  permaneció idéntica después de emitir v2. La descarga diaria tenía dos planillas
  con el código institucional y el paciente ficticio esperado.
- `db.sqlite3` y el logotipo original conservan sus bytes respecto de HEAD;
  `config/admin.txt` no presenta cambios de contenido (solo la diferencia CRLF/LF
  del checkout Windows al compararlo directamente con el blob de Git).

## Probar en el navegador sin tocar la base original

Abrir PowerShell y ejecutar:

```powershell
Set-Location -LiteralPath 'C:\Users\wilfr\OneDrive\Datos adjuntos\Documents\GitHub\SistmaHistoriaClinicaYControlMedicoDiario'
.\.venv-phase1\Scripts\python.exe -B -m pip install -r requirements-dev.txt
.\.venv-phase1\Scripts\python.exe -B scripts\preview_medical_system.py --port 8006
```

El entorno `.venv-phase1` debe existir; las instrucciones para crearlo están en
[Fase 1](FASE1.md). El script crea otra carpeta `.uptag-demo-...` con su propia
`demo.sqlite3`, aplica allí todas las migraciones y muestra tres credenciales
aleatorias ficticias. Ignora `DJANGO_DB_PATH` heredada y fuerza Caracas. No abre ni
migra `db.sqlite3`. No copiar esta demo sobre una base existente.

Abrir **http://127.0.0.1:8006/** y usar las credenciales impresas en esa ejecución.
Usar un puerto libre; si está ocupado, cambiar `--port` y abrir la URL impresa.
No reutilizar un servidor anterior: la demo funciona sin recarga automática.
Ctrl+C detiene el servidor sin borrar la base creada.

### Recorrido de médico

1. En **Atenciones**, hay una pendiente, una en atención, dos atendidas y una
   cancelada. Abrir **Pacientes** para comprobar las cinco categorías y una ficha
   histórica Por verificar. Registrar un paciente no crea una consulta.
2. Abrir **Registro Médico Diario** y consultar hoy. Deben aparecer solamente las
   dos atendidas, separadas por equipo/turno. Probar una fecha vacía y un rango:
   dejar vacío el campo Fecha al introducir Desde/Hasta. El PDF contiene planillas
   por cada fecha, con páginas adicionales cuando corresponda. Las ocho casillas
   se imprimen como X y las no marcadas permanecen vacías. No se inventan datos
   de especialidad ni cédula del médico.
3. Abrir **Pacientes pendientes**. Muestra solo el estado pendiente actual, con
   filtros por fecha de llegada. No incluye iniciadas, atendidas ni canceladas;
   dispone de un enlace independiente para consultar pacientes en atención.
4. Abrir la consulta de **Muestra 03** desde su expediente: tiene las ocho opciones.
   Comprobar su PDF FOR-SSS-04. **Corregir** requiere motivo; cambiar enfermedad
   actual a `Muestra ficticia: β y CO₂.` permite comprobar tipografía y auditoría.
   Revisar los valores anteriores/nuevos en el detalle. Las opciones se dividen
   en RP/T de C y Tto/Lab/Ref/Imag/Rx/Cit; no se interpretan sus abreviaturas.
5. La consulta de Muestra 03 tiene un reposo borrador y la de Muestra 05, uno ya
   emitido. Revisar el borrador y su vista previa con marca de agua, confirmar la
   revisión y aprobar. Descargar v1. Preparar otra versión desde la emitida,
   introducir motivo de corrección, guardar, revisar y aprobar v2. Deben conservarse
   el enlace a v1, su aprobador, fecha, datos y SHA-256 originales. Descargar v1
   nuevamente y comparar ambos archivos con `Get-FileHash -Algorithm SHA256`.
6. Descargar los tres PDF y abrirlos en el visor. Imprimir en A4 horizontal para
   FOR-SSS-02 y A4 vertical para los otros, a tamaño real. El botón Imprimir abre
   la vista protegida con controles del visor; no se envió ninguna impresión física
   durante esta revisión.

### Recorrido de enfermería y administración

Cerrar sesión con el botón y entrar con las otras cuentas de la misma demo.
Enfermería puede registrar llegadas, iniciar atención y descargar el diario, pero
no redactar ni emitir documentos clínicos. Administración puede consultar historias
en pantalla y gestionar cuentas, sin modificar clínica ni aprobar reposos.
Probar las URL copiadas de la sesión médica: las acciones/documentos prohibidos
deben devolver acceso denegado incluso cuando se conoce el identificador.

## Repetir pruebas y generar muestras independientes

```powershell
.\.venv-phase1\Scripts\python.exe -B manage.py test --settings=config.test_settings --verbosity=1
.\.venv-phase1\Scripts\python.exe -B manage.py check --settings=config.test_settings
.\.venv-phase1\Scripts\python.exe -B manage.py makemigrations --check --dry-run --settings=config.test_settings
.\.venv-phase1\Scripts\python.exe -B scripts\verify_account_migrations_synthetic.py
.\.venv-phase1\Scripts\python.exe -B -m pip check
.\.venv-phase1\Scripts\python.exe -B scripts\preview_daily_pdf.py
.\.venv-phase1\Scripts\python.exe -B scripts\preview_history_pdf.py
.\.venv-phase1\Scripts\python.exe -B scripts\preview_reposo_pdf.py
```

Las muestras usan bases en memoria y se guardan en `output/pdf/`, excluido de Git.
Los tests emplean SQLite independiente y correo locmem; no ejecutar pruebas sin
`--settings=config.test_settings` sobre una configuración que apunte a datos reales.

## Migración nueva y eventual ensayo con una copia

La 0010 añade exclusivamente los dos triggers descritos. No cambia columnas,
identificadores, hashes, PDF ni datos. Es reversible retirando esas dos guardas,
pero revertirla reduce la protección: no se recomienda como recuperación. No
retroceder la 0009, porque eliminaría la tabla de documentos.

La demo anterior ya permite probar todo sin copiar datos reales. Si posteriormente
se desea ensayar una actualización de una base existente, seguir el respaldo
SQLite de solo lectura y el administrador inicial de
[Revisión de migraciones](REVISION_MIGRACIONES_FASE1.md). Apuntar `DJANGO_DB_PATH`
expresamente a una **copia privada independiente**, comprobar la ruta y revisar
`showmigrations` y `migrate --plan` antes de migrar esa copia. No usar `--fake`.
Si la 0009 ya estaba aplicada, la 0010 sigue siendo necesaria. Aplicar migraciones
al original continúa pendiente de autorización; no se realizó en esta revisión.

## Archivos de esta revisión

- Validación y fechas: `Hisotria_clinica/services.py`, `medical_time.py`,
  `reports.py`, `views.py`.
- PDF y revisión: `pdf_reports.py`, `pdf_reposos.py`, `reposos.py`,
  `base/static/base/fonts/DejaVuSans.ttf`, `LICENSE-DejaVu.txt`.
- Migración: `Hisotria_clinica/migrations/0010_protect_issued_replacements.py`.
- Regresiones: `test_phase2_integration.py`, `test_migrations.py`, `test_reports.py`.
- Demo y muestras: los cuatro scripts `scripts/preview_*.py`.
- Documentación: esta guía, README y nota de actualización en la guía de reposos.

## Límites y recomendaciones pendientes

Los textos que exceden el espacio institucional o contienen caracteres no cubiertos
por la fuente bloquean la emisión con error comprensible; no se recortan ni alteran
datos para hacerlos caber. La historia PDF reproduce únicamente la hoja suministrada.
La firma y el sello requieren el procedimiento institucional; no se simulan.

La protección SQLite no impide que alguien con control total del archivo retire
deliberadamente los triggers. Mantener respaldos privados completos, permisos del
archivo y comprobar su restauración. Toda futura reconstrucción de la tabla de
reposos debe reinstalar los cuatro triggers y pasar las pruebas de conservación.
La base crece con los PDF guardados. Los secretos publicados previamente requieren
rotación y los archivos sensibles versionados requieren una decisión explícita de
retirada; no se borraron ni se reescribió el historial. Esta verificación local no
sustituye la configuración de producción, HTTPS, correo y respaldos institucionales.
