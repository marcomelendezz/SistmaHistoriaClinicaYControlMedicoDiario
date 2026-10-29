# Fase 2: reportes web del servicio médico

Esta guía describe la primera entrega web. La ampliación posterior incorpora
[ocho opciones y el PDF FOR-SSS-02](FASE2_OPCIONES_PDF.md), con la migración 0007
y 136 pruebas; sustituye los pendientes de PDF diario indicados aquí.

## Alcance y criterios

Implementación en `feature/uptag-medical-system-v2`. Conserva las cinco categorías,
el indicador temporal Por verificar, los expedientes, el flujo de atención y las
auditorías anteriores. No reconstruye tablas ni aplica migraciones al SQLite original.
No añade dependencias. **El PDF FOR-SSS-02 queda pendiente del formato oficial
legible**, por instrucción del usuario; estas pantallas no sustituyen la planilla.

El menú de médicos y enfermeras activos y aprobados incorpora:

- **Registro Médico Diario:** una fecha o rango inclusivo de hasta 366 días.
  Presenta cada fecha, incluso sin resultados, y grupos independientes por médico
  de la historia, enfermera responsable y turno expresamente registrados.
- **Pacientes pendientes:** todas las llegadas que siguen pendientes actualmente,
  o las que llegaron en una fecha/rango. No incluye En atención, Atendido ni
  Cancelado y no reconstruye el estado histórico al cierre de otro día.

El diario utiliza la fecha de finalización en **America/Caracas**. Una visita que
llega antes de medianoche y termina después pertenece al día en que termina.
La fecha clínica editable de la historia no traslada esa finalización.
Cada atención completada aparece una vez; diferentes visitas del mismo paciente
se cuentan por separado. No se cuentan pendientes ni cancelaciones.

Solo se incluyen atenciones con historia del mismo paciente, médico registrado,
campos clínicos obligatorios completos y transición trazable a Atendido. Las
inconsistencias se advierten fuera de los totales. Las consultas antiguas sin
atención vinculada se muestran como referencias separadas según su fecha clínica;
no se inventan llegadas, médicos, responsables ni estados para incluirlas.
Las listas de advertencias muestran hasta 50 referencias y el total real.

El diario presenta paciente/cédula, categoría actual, edad calculada al finalizar
desde el nacimiento, sexo, diagnóstico completo y responsable/hora de cierre.
Los datos clínicos y personales mostrados son los vigentes, con su auditoría;
este reporte web no es una instantánea oficial inmutable. El reporte de pendientes
no incorpora diagnósticos. No se inventan especialidades, servicios o procedimientos.

En Nueva Consulta se pueden registrar, opcionalmente, turno y enfermera responsable.
El servidor solo acepta una enfermera activa y aprobada para ese campo. La persona
que registra la llegada no se asigna automáticamente como enfermera responsable.
Un valor ausente aparece como Sin registrar. Las atenciones antiguas mantienen
estos campos vacíos y no se actualizan automáticamente.

Los reportes exigen permisos tanto en las vistas como en los servicios/consultas.
No conceden escritura clínica a enfermería ni permisos médicos al administrador
o a un superusuario técnico. Solo admiten GET/HEAD y envían encabezados privados
de no almacenamiento en caché. Consultarlos no escribe auditorías ni registros.

## Cambios y migración

| Archivos | Cambio |
| --- | --- |
| `Hisotria_clinica/reports.py` | Consultas de reportes, validación de períodos, agrupaciones y advertencias. |
| `models.py`, `services.py`, `forms.py` de la misma aplicación | Equipo opcional en llegadas y filtros de reportes. |
| `views.py`, `urls.py`, `templates/historia/reportes/` | Dos vistas web y plantillas con tablas desplazables. |
| `LoginRegister/access.py`, `context_processors.py` | Capacidad de lectura de reportes para médicos y enfermeras aprobados. |
| `base/templates/base/header_navbar.html`, `base/static/base/css/styleheadernav.css` | Enlaces e interfaz institucional adaptable. |
| `Hisotria_clinica/test_reports.py`, `test_migrations.py` | Pruebas de reportes y conservación de datos previos. |
| `scripts/preview_medical_system.py` | Demo nueva con pendientes y dos grupos de atenciones completadas. |

Nueva migración: **`Hisotria_clinica.0006_attention_report_team`**, dependiente de
0005. Añade `enfermera_responsable` nullable con relación PROTECT y `turno` opcional
en Atencion. No contiene operaciones de datos ni clasificaciones automáticas.
Mantiene identificadores, columnas anteriores, historias, estados y auditorías.
Revertirla descartaría la información nueva de equipo: no usar una reversión como
procedimiento de recuperación de datos. No se modificaron migraciones anteriores.

## Visualizar con una SQLite nueva y ficticia

En PowerShell, desde la carpeta del repositorio:

```powershell
Set-Location -LiteralPath 'C:\Users\wilfr\OneDrive\Datos adjuntos\Documents\GitHub\SistmaHistoriaClinicaYControlMedicoDiario'
.\.venv-phase1\Scripts\python.exe -B scripts\preview_medical_system.py --port 8003
```

El script crea una carpeta `.uptag-demo-...`, aplica las migraciones exclusivamente
a su nueva SQLite y muestra credenciales aleatorias para los tres roles. Ignora
`DJANGO_DB_PATH` heredada. No abre ni migra `db.sqlite3`, no limpia demostraciones
anteriores y solo escucha en localhost. Si el puerto está ocupado, elegir otro.

Abrir `http://127.0.0.1:8003/` e ingresar con el médico o la enfermera ficticios.
En el menú están Registro Médico Diario y Pacientes pendientes:

```text
http://127.0.0.1:8003/historia/reportes/registro-diario/
http://127.0.0.1:8003/historia/reportes/pendientes/
```

El diario comienza en el día actual de Caracas. Para un rango, vaciar Una fecha y
completar Desde/Hasta. Para pendientes de cualquier fecha, dejar los tres vacíos.
El rango máximo es de 366 días inclusive; rangos inválidos muestran errores sin
ejecutar un reporte alternativo. La demo tiene dos atenciones completadas en turnos
distintos, una pendiente, una en atención y una cancelada. No introducir datos reales.
Ctrl+C detiene el servidor. Reiniciar el script crea otra demo independiente.

## Ensayo de migración con datos existentes

La aplicación al SQLite original sigue sin autorización. Para una copia privada,
seguir el respaldo SQLite de solo lectura y la secuencia del primer administrador
en [la revisión de Fase 1](REVISION_MIGRACIONES_FASE1.md), y el apartado
[Ensayo sobre una copia privada](CORRECCIONES_PACIENTES_ATENCION.md#ensayo-sobre-una-copia-privada-de-tu-base).
Detener escritores antes del respaldo; conservar una copia previa independiente.

Configurar `DJANGO_DB_PATH` explícitamente a **ensayo.sqlite3**, nunca al original,
y las variables de entorno de esas guías. Revisar `showmigrations` y `migrate --plan`
antes de avanzar. Si las migraciones de cuentas 0003/0004 no están aplicadas,
completar primero el procedimiento seguro de `bootstrap_admin` y su verificación.
No solicitar una migración anterior ya superada ni utilizar `--fake`.

Con la copia y el administrador ya preparados:

```powershell
.\.venv-phase1\Scripts\python.exe -B manage.py showmigrations --settings=config.settings
.\.venv-phase1\Scripts\python.exe -B manage.py migrate --plan --settings=config.settings
# Continuar solo tras verificar que DJANGO_DB_PATH apunta a la copia y el plan es correcto.
.\.venv-phase1\Scripts\python.exe -B manage.py migrate --settings=config.settings
if ($LASTEXITCODE -ne 0) { throw 'La migración falló. No iniciar el servidor.' }
.\.venv-phase1\Scripts\python.exe -B manage.py check --settings=config.settings
.\.venv-phase1\Scripts\python.exe -B manage.py runserver 127.0.0.1:8003 --noreload --settings=config.settings
```

Comparar columnas originales e integridad de claves como indican las guías.
No copiar el archivo de ensayo o la demo sobre el original. `config.test_settings`
es exclusivamente para pruebas automatizadas en memoria, no para este navegador.

## Verificación realizada

```powershell
.\.venv-phase1\Scripts\python.exe -B manage.py test --settings=config.test_settings --verbosity=1
.\.venv-phase1\Scripts\python.exe -B manage.py makemigrations --check --dry-run --settings=config.test_settings
.\.venv-phase1\Scripts\python.exe -B scripts\verify_account_migrations_synthetic.py
.\.venv-phase1\Scripts\python.exe -B -m pip check
```

- **114 pruebas aprobadas** con Django 5.2.18 y también con Django 5.2.7.
- 26 pruebas de reportes: permisos HTTP/servicios, caché, rangos y errores,
  medianoche Caracas, año bisiesto, 366 días, agrupaciones, edades, categorías,
  diagnósticos escapados/completos, ausencia de duplicación y consultas sin escrituras.
- Prueba de migración 0005→0006 con atención, paciente, historia y auditorías
  ficticios existentes: todas sus columnas previas se conservan; no se infiere
  enfermera desde quien registró la llegada. Integridad y claves foráneas válidas.
- Ensayo físico desde esquemas 0002: conserva ocho cuentas históricas, contraseñas,
  permisos, relaciones y datos médicos sintéticos. Administrador inicial verificado.
- Django y `makemigrations --check`: sin incidencias. `pip check`: sin conflictos.
- Navegador con datos ficticios: consulta diaria, rango con día vacío, grupos por
  turno y reporte de pendientes. Formularios y tablas adaptables a móvil.

Capturas con datos ficticios: [diario en computadora](qa/registro-diario-desktop.jpg)
y [diario en móvil](qa/registro-diario-mobile.jpg).

No se publicaron cambios ni se migró el original. PDF institucional pendiente;
se conserva el trabajo de autenticación, permisos y auditorías anterior.
