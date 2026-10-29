# Fase 1 — Autenticación, aprobación y autorización

## Alcance y estado

Este documento conserva el alcance de la entrega inicial. Las correcciones
posteriores (pacientes, motivo administrativo opcional y atención) y su ejecución
vigente están en [la guía de pacientes y atención](CORRECCIONES_PACIENTES_ATENCION.md).

Para el error de columna `requested_role` pendiente y el ensayo de actualización
en Windows, consulta [la revisión específica de 0003/0004](REVISION_MIGRACIONES_FASE1.md).
Esa revisión posterior incorpora la conservación exacta de hashes antiguos al
verificar al administrador; la suite actualizada contiene 54 pruebas aprobadas.

Rama: `feature/uptag-medical-system-v2`. Se conserva el proyecto Django, el
modelo `LoginRegister.Usuario`, los identificadores, contraseñas y relaciones
existentes. No se aplicaron migraciones sobre `db.sqlite3`, no se modificaron
registros médicos y no se hicieron commits, push, PR ni despliegues.

Esta fase permite solicitar cuentas, aprobar/rechazar solicitudes, asignar roles,
activar/desactivar cuentas y consultar una auditoría administrativa. Se protege
la funcionalidad clínica existente y se separa el registro personal del paciente
de la creación de una consulta. No se implementan aún atenciones, correcciones
clínicas, antecedentes, constancias, PDF ni indicadores de las siguientes fases.

## Entorno y dependencias

Base comprobada: Python 3.12.10. Se conserva Django 5.2, la línea del entorno
original, actualizada a **5.2.18** en un entorno virtual independiente. No se
cambia el Python ni se actualiza el Django global instalado. Las cinco
dependencias están fijadas en `requirements.txt`, convertido de UTF-16 a UTF-8:

| Dependencia | Versión fijada |
| --- | --- |
| Django | 5.2.18 |
| django-axes | 8.3.1 |
| asgiref | 3.11.1 |
| sqlparse | 0.5.5 |
| tzdata | 2026.2 |

No se añadió una biblioteca de aplicación. La declaración antigua de Django
6.0.4 no coincidía con el entorno. Se decidió mantener la línea 5.2 para evitar
un salto mayor innecesario. Django publicó 5.2.18 como actualización de seguridad:
https://www.djangoproject.com/weblog/2026/oct/06/security-releases/

Instalación en PowerShell desde la raíz del proyecto:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

En los comandos siguientes, `python` debe ser el ejecutable de ese entorno.
Puede emplearse su ruta completa sin activar el entorno. El entorno local de
verificación de esta entrega se llama `.venv-phase1` y está excluido de Git.

## Configuración por entorno

`.env.example` es una referencia sin secretos; **no se carga automáticamente**.
Configura las variables en el proceso del servidor o en su gestor de secretos.
No publiques una copia completada. La aplicación se niega a iniciar si falta
`DJANGO_SECRET_KEY`.

| Variable | Uso |
| --- | --- |
| `DJANGO_SECRET_KEY` | Clave aleatoria nueva y privada; nunca la publicada. |
| `DJANGO_DEBUG` | `false` en producción; `true` solo en desarrollo local. |
| `DJANGO_ALLOWED_HOSTS` | Hosts reales separados por comas, sin comodín global. |
| `DJANGO_DB_PATH` | Ruta absoluta a la base elegida, fuera del repositorio. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Orígenes HTTPS autorizados separados por comas. |
| `DJANGO_HSTS_SECONDS` | Inicialmente `0`; aumentar solo tras validar HTTPS. |
| `DJANGO_HSTS_INCLUDE_SUBDOMAINS` | `false`; activar solo si todos los subdominios admiten exclusivamente HTTPS. |
| `DJANGO_HSTS_PRELOAD` | `false`; requiere decisión institucional sobre precarga HSTS. |
| `EMAIL_BACKEND` | Backend SMTP en operación; `locmem` exclusivamente en pruebas. |
| `EMAIL_HOST`, `EMAIL_PORT` | Servidor y puerto facilitados por la institución. |
| `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | Credenciales nuevas, privadas. |
| `EMAIL_USE_TLS`, `EMAIL_USE_SSL` | Configurar según el proveedor; no activar ambos. |
| `DEFAULT_FROM_EMAIL` | Remitente institucional autorizado. |

Por compatibilidad, si no defines `DJANGO_DB_PATH`, Django apunta al SQLite
existente. **Define la ruta explícitamente antes de cualquier migración.** No
uses ese valor predeterminado durante pruebas. La entrega inicial utilizaba UTC; las correcciones de atención presentan las
fechas en America/Caracas mediante `DJANGO_TIME_ZONE`, sin reescribir timestamps históricos.

Con `DEBUG=false` se exige HTTPS mediante redirección y cookies seguras.
Para desarrollo local por HTTP utiliza `DJANGO_DEBUG=true` y hosts locales.
No configures confianza en cabeceras de proxy sin validar que el proxy elimina
cabeceras externas y controla todas las conexiones de entrada.

## Primer administrador y aplicación segura de migraciones

Esta secuencia es un **procedimiento para el operador autorizado**, no una
migración de producción ejecutada durante esta entrega.

1. Mantener el servicio en mantenimiento: detener procesos web, tareas y otros
   escritores. No servir simultáneamente versiones antiguas y nuevas del código.
2. Crear y verificar una copia de seguridad consistente de la base y sus archivos
   asociados mediante el procedimiento institucional. Probar su restauración en
   un entorno privado. No incorporar copias ni datos reales al repositorio.
3. Configurar el entorno virtual, una clave nueva y `DJANGO_DB_PATH` con la ruta
   exacta de la base de destino. Revisar `showmigrations` y `migrate --plan`.
4. En una instalación que aún está en la migración 0002, aplicar **solo el esquema
   0003 de LoginRegister**. No ejecutar todavía el `migrate` general:

   ```powershell
   python manage.py migrate LoginRegister 0003 --plan
   python manage.py migrate LoginRegister 0003
   ```

   `0003_account_approval_schema` añade campos y auditoría. Las cuentas existentes
   reciben el marcador `legacy`. No cambia contraseñas, `cargo`, grupos,
   identificadores ni registros clínicos. La nueva autorización cierra el acceso
   de estas cuentas, por lo que el servicio debe seguir en mantenimiento hasta
   disponer del administrador verificado. Las nuevas cuentas nacen pendientes.

5. Crear un administrador mediante contraseña interactiva (sustituir los valores
   de ejemplo por los datos del operador institucional):

   ```powershell
   python manage.py bootstrap_admin --email operador@example.invalid --nombre Administrador --apellido Institucional
   ```

   La contraseña se solicita sin mostrarla, se confirma y pasa los validadores
   de Django, incluido el mínimo de 16 caracteres. No se admite contraseña como
   argumento, no se imprime ni se incluye en la auditoría. El comando no otorga
   facultades clínicas ni convierte automáticamente la cuenta en superusuario.

   Para **designar explícitamente una cuenta existente**, conservando su hash,
   identificador y relaciones:

   ```powershell
   python manage.py bootstrap_admin --email operador@example.invalid --designate-existing
   ```

   Exige verificar su contraseña actual. Nunca la reemplaza. Si el correo coincide
   con varias cuentas antiguas al ignorar mayúsculas, el comando se detiene. Una
   cuenta sin contraseña utilizable no puede designarse de esta manera: crear un
   administrador nuevo es la alternativa segura. El acceso local a este comando
   debe restringirse a operadores autorizados.

6. Verificar otra vez al administrador, aún en mantenimiento:

   ```powershell
   python manage.py bootstrap_admin --email operador@example.invalid --verify
   ```

   Verifica contraseña, estado activo, aprobación y rol administrativo. Registra
   `bootstrap_verified` y restablece los intentos de bloqueo de esa cuenta si
   existen las tablas de Axes. No modifica su contraseña. La administración
   institucional se realiza en **`/cuentas/`**, sin exigir `is_staff`.

7. Revisar y completar las migraciones:

   ```powershell
   python manage.py migrate --plan
   python manage.py migrate
   python manage.py check
   python manage.py check --deploy
   ```

   `0004_review_legacy_accounts` comprueba que existe un administrador activo,
   aprobado y con verificación registrada antes de convertir cuentas `legacy`
   en pendientes. Si falta, falla de forma transaccional. Las instalaciones
   vacías no requieren esta conversión, pero igualmente deben crear su primer
   administrador antes de admitir solicitudes.

8. Antes de reabrir el servicio, comprobar el login del administrador, `/cuentas/`
   y una cuenta ficticia con permisos mínimos en un entorno de ensayo. Confirmar
   recuperación de contraseña con el correo institucional configurado. Después,
   el administrador deberá verificar la identidad y facultades de cada usuario
   antes de aprobarlo. No usar registros médicos reales como casos de prueba.

No repetir `migrate LoginRegister 0003` indiscriminadamente en una instalación ya
actualizada: esa orden solicita una reversión de `0004`. Consultar siempre el
plan antes de ejecutar una migración.

### Conservación y reversión

`cargo` se conserva exactamente como estaba. Valores reconocidos como `Medico`
solo precargan el **rol solicitado**; no confirman una autorización profesional.
Los valores ambiguos quedan sin rol solicitado. Ni los grupos ni `is_staff` ni
`is_superuser` conceden permisos médicos o aprobación institucional por sí solos.
Ante la ausencia de una aprobación verificable, toda cuenta antigua requiere
revisión, excepto el administrador designado explícitamente.

`0004` tiene una reversión que restaura la clasificación previa únicamente para
cuentas que continúan sin revisión; conserva las decisiones posteriores y añade
un evento de reversión sin borrar la auditoría. Revertir la clasificación tampoco
habilita acceso médico a cuentas `legacy` bajo este código.

**No revertir por debajo de 0003 ni desplegar el código antiguo como mecanismo de
recuperación ordinario.** Quitar el esquema perdería los campos de aprobación y
auditoría; el código anterior carece de los controles nuevos. Restauraciones y
reversiones de producción requieren un plan específico y autorización.

## Roles y operación

| Operación disponible en esta fase | Enfermera | Médico | Administrador |
| --- | --- | --- | --- |
| Registrar datos personales de paciente | Sí | Sí | No |
| Buscar pacientes y leer consultas | Sí | Sí | Sí |
| Crear consultas con diagnóstico/tratamiento | No | Sí | No |
| Aprobar, rechazar y asignar roles | No | No | Sí |
| Activar/desactivar otras cuentas | No | No | Sí |
| Consultar auditoría administrativa | No | No | Sí |

El administrador puede asignar un rol distinto del solicitado, con motivo
obligatorio. No puede cambiar su propia autorización ni desactivarse a sí mismo;
así se conserva al menos el administrador que realiza la decisión. Puede designar
otro administrador y este podrá revisar la primera cuenta cuando corresponda.

Las decisiones y sus valores anteriores/nuevos se guardan en una transacción.
La pantalla de auditoría muestra los últimos 200 eventos y no ofrece edición ni
borrado. Este registro administrativo no sustituye la auditoría clínica futura.
La protección no cubre a un operador con acceso directo privilegiado a la base;
la institución debe restringir ese acceso y proteger sus copias.

Los controles vuelven a consultar la cuenta actual y se aplican en vistas,
servicios y consultas. Una sesión abierta pierde el permiso al cambiar la
autorización; al desactivar la cuenta, Django deja de autenticarla. Las consultas
clínicas están disponibles para los tres roles aprobados conforme al expediente
central institucional. Los identificadores no permiten saltarse esta política.
Los servicios de escritura son exclusivos del médico. Las lecturas clínicas y
administrativas protegidas llevan cabeceras para impedir su almacenamiento en caché.

La aprobación administrativa no equivale a habilitación médica. En esta fase un
administrador no redacta consultas, aunque tenga banderas de superusuario. La
autorización médica diferenciada para emisión de constancias se resolverá cuando
se implemente esa función; actualmente no existe emisión de documentos.

El registro público permite solicitar médico o enfermera; se ignoran campos de
privilegio enviados por el cliente. Los pendientes/rechazados no pueden iniciar
sesión ni acceder a módulos mediante una sesión antigua. El perfil propio no
permite modificar roles, aprobación ni privilegios.

## Contraseñas, correo y Axes

Se conservan las vistas y tokens de recuperación de Django. El enlace vence en
una hora, el token deja de ser válido al cambiar la contraseña y el proceso no
aprueba cuentas. El cierre de sesión usa POST con CSRF; GET no termina sesiones.

Se conserva `django-axes`: tres fallos activan el bloqueo por combinación de
cuenta e IP. El bloqueo de otra cuenta en una red compartida no impide iniciar
sesión al administrador. `AXES_USERNAME_FORM_FIELD='username'` coincide con el
campo de `AuthenticationForm`, aunque su contenido sea el correo: evita que los
fallos se registren sin identificar la cuenta. Recuperar
la contraseña mediante un token válido restablece los intentos de esa cuenta.
SMTP no se prueba con credenciales reales en la suite. Antes de operar, la
institución debe configurar y validar envío, dominio de los enlaces, remitente y
políticas de entrega. No usar el backend de consola con usuarios reales, pues
expone los enlaces de recuperación en los registros.

## Pruebas y comprobaciones

```powershell
python manage.py test --settings=config.test_settings --verbosity=2
python manage.py check --settings=config.test_settings
python manage.py makemigrations --check --dry-run --settings=config.test_settings
python -m pip check
```

`config.test_settings` fuerza SQLite en memoria y correo en memoria, sin abrir
`db.sqlite3` ni utilizar SMTP. Incluye una clave sintética y un hasher rápido
**exclusivamente para pruebas**. Nunca se debe usar esa configuración para servir
la aplicación. Los tests de migración usan usuarios, grupos y consultas ficticias.

La suite verifica registro, aprobación/rechazo, cambio de roles, activación,
revocación sobre sesiones abiertas, CSRF, acceso administrativo, peticiones
clínicas directas, lectura por objeto, servicios, transacciones, tokens,
contraseñas, cierre de sesión, Axes, administrador inicial y migración/reversión.

El chequeo `--deploy` con la configuración de pruebas emite advertencias de HTTPS
y cookies porque esa configuración deshabilita intencionadamente HTTPS para el
cliente de tests. Ejecutar el chequeo de despliegue con **`config.settings` y las
variables de producción**. HSTS permanece en cero hasta validar HTTPS y fijar su
política; no se debe silenciar esa advertencia sin revisar la infraestructura.

## Archivos y puntos de revisión

- `LoginRegister/models.py`, `forms.py`, `views.py`, `urls.py`: cuentas y aprobación.
- `LoginRegister/access.py`, `services.py`, `context_processors.py`: autorización,
  auditoría y navegación.
- `LoginRegister/admin_apps.py`, `admin_site.py`: acceso restringido al admin Django.
- `LoginRegister/management/commands/bootstrap_admin.py`: administrador por consola.
- `LoginRegister/migrations/0003_account_approval_schema.py` y
  `0004_review_legacy_accounts.py`: actualización escalonada.
- Plantillas `LoginRegister/accounts/{list,review,audit}.html`: administración.
- `Hisotria_clinica/{forms,views,urls,services}.py`, plantillas de paciente,
  detalle y listado: protección de operaciones existentes y lectura independiente.
- `dashboard/views.py`, plantilla del panel y plantillas base: accesos y logout.
- Tests existentes y `LoginRegister/test_security.py`, `test_migrations.py`,
  `Hisotria_clinica/test_access.py`: regresión y seguridad con datos ficticios.
- `config/settings.py`, `test_settings.py`, `.env.example`, `.gitignore`,
  `requirements.txt`, `README.md` y este documento: entorno y operación.

## Riesgos que requieren actuación institucional

- Revocar la credencial SMTP publicada y generar una nueva `SECRET_KEY`. Retirar
  los literales del código no invalida lo expuesto en versiones anteriores. La
  rotación de la clave invalida sesiones y tokens previos: planificar el corte.
  No reintroducir la clave comprometida en `SECRET_KEY_FALLBACKS`.
- La SQLite, `config/admin.txt` y bytecode ya versionados continúan presentes,
  por instrucción del usuario. `.gitignore` evita nuevas incorporaciones, pero no
  sanea archivos seguidos ni el historial. Revisar su exposición y autorizar por
  separado su retirada y cualquier tratamiento del historial. No publicar esta
  rama mientras siga pendiente esa revisión.
- No se verificó el contenido personal de la base. Antes de futuras migraciones
  de pacientes se necesita una revisión controlada de calidad de datos. La relación
  clínica `CASCADE` existente no se modificó en esta fase; no hay pantallas de
  eliminación definitiva de historias implementadas aquí.
- HTTPS, proxy, respaldos, permisos del sistema operativo, protección del correo,
  retención de auditoría y acceso del personal a datos clínicos requieren medidas
  operativas adicionales. Este cambio local no constituye un despliegue validado.
- Las fotos de la historia clínica muestran solo la página 1 de 3. Las páginas
  restantes y la adaptación institucional de constancias para personal quedan
  pendientes de aclaración antes de la fase de documentos.


## Resultado de la verificación ejecutada

Fecha: 27 de octubre de 2026. Todas las verificaciones usaron datos ficticios.

| Comprobación | Resultado |
| --- | --- |
| Suite con Django 5.2.18 y requisitos fijados en `.venv-phase1` | 53 pruebas aprobadas, 0 fallos. |
| Compatibilidad con Django 5.2.7 del Python global original | Las mismas 53 pruebas aprobadas, 0 fallos. No se recomienda esa versión antigua para desplegar. |
| `check` con configuración de pruebas | Sin errores ni advertencias. |
| `makemigrations --check --dry-run` | Sin cambios pendientes. |
| `pip check` en el entorno aislado | Sin requisitos incompatibles. |
| `check --deploy` con variables sintéticas, HTTPS, cookies seguras y HSTS configurado | Sin incidencias; es una simulación de configuración, no una validación de infraestructura real. |
| Hasher con configuración operativa | PBKDF2-SHA256; el hasher rápido está limitado a pruebas. |
| Comparación de la SQLite, archivo administrativo y logotipo frente a Git | Contenido sin cambios. |
| Revisión sintáctica de fuentes y `git diff --check` | Sin incidencias. |

Se verificó tanto la creación del administrador antes de instalar las tablas de
Axes como la actualización con cuentas antiguas. La migración de revisión falla
sin administrador verificado y conserva usuarios, contraseñas, grupos y consultas
ficticias. La reversión preserva las decisiones administrativas posteriores.

Durante la integración se corrigieron la ruta predeterminada del login, la prueba
antigua que intentaba crear historias sin autenticación, los mensajes de validación
y la identificación del usuario en Axes. Las últimas ejecuciones completas pasan.
SMTP real, HTTPS del servidor y aplicación a una base operativa quedan pendientes
del procedimiento institucional de puesta en marcha. Las variables HSTS de la
simulación no se activaron sobre ningún servidor real.

## Inventario exacto de archivos de esta entrega

La revisión posterior añadió `docs/REVISION_MIGRACIONES_FASE1.md` y
`scripts/verify_account_migrations_synthetic.py`.

- `.env.example`
- `.gitignore`
- `Hisotria_clinica/forms.py`
- `Hisotria_clinica/services.py`
- `Hisotria_clinica/templates/historia/detalle.html`
- `Hisotria_clinica/templates/historia/lista_historia.html`
- `Hisotria_clinica/templates/historia/paciente.html`
- `Hisotria_clinica/test_access.py`
- `Hisotria_clinica/tests.py`
- `Hisotria_clinica/urls.py`
- `Hisotria_clinica/views.py`
- `LoginRegister/access.py`
- `LoginRegister/admin_apps.py`
- `LoginRegister/admin_site.py`
- `LoginRegister/context_processors.py`
- `LoginRegister/forms.py`
- `LoginRegister/management/__init__.py`
- `LoginRegister/management/commands/__init__.py`
- `LoginRegister/management/commands/bootstrap_admin.py`
- `LoginRegister/migrations/0003_account_approval_schema.py`
- `LoginRegister/migrations/0004_review_legacy_accounts.py`
- `LoginRegister/models.py`
- `LoginRegister/services.py`
- `LoginRegister/templates/LoginRegister/accounts/audit.html`
- `LoginRegister/templates/LoginRegister/accounts/list.html`
- `LoginRegister/templates/LoginRegister/accounts/review.html`
- `LoginRegister/templates/LoginRegister/register.html`
- `LoginRegister/test_migrations.py`
- `LoginRegister/test_security.py`
- `LoginRegister/tests.py`
- `LoginRegister/urls.py`
- `LoginRegister/views.py`
- `README.md`
- `base/templates/403.html`
- `base/templates/base/baselogin.html`
- `base/templates/base/header_navbar.html`
- `config/settings.py`
- `config/test_settings.py`
- `dashboard/templates/dashboard/dashboard.html`
- `dashboard/tests.py`
- `dashboard/views.py`
- `docs/FASE1.md`
- `requirements.txt`
