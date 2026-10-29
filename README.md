# Sistema de Gestión Médica UPTAG

Aplicación Django existente, ampliada incrementalmente. Esta entrega implementa
la **Fase 1: seguridad, autenticación y roles**, y las correcciones autorizadas de
clasificación de pacientes, aprobación administrativa y flujo de atención. Incluye
los reportes web de la **Fase 2**, por fecha/rango y pendientes separados.
El PDF diario FOR-SSS-02 incorpora las ocho opciones institucionales, con 17 filas
por página. La Historia Clínica FOR-SSS-04 genera la única hoja suministrada por
consulta, con datos completos y permisos médicos. La Constancia de Reposo
FOR-SSS-07 incorpora borrador, revisión, aprobación médica y PDF inmutable por versión.

La [revisión integral de Fase 2](docs/REVISION_INTEGRAL_FASE2.md) documenta los
fallos corregidos, las 211 pruebas aprobadas, la migración protectora 0010 y el
recorrido de navegador con una base ficticia independiente.

Consulta [la guía vigente de pacientes y atención](docs/CORRECCIONES_PACIENTES_ATENCION.md)
y [los reportes de Fase 2](docs/FASE2_REPORTES.md), junto con
[la guía de Fase 1](docs/FASE1.md), antes de instalar, migrar o iniciar el
servidor. Contiene la configuración, el procedimiento obligatorio del primer
administrador, pruebas y límites de esta entrega.

La ampliación de casillas, permisos, auditoría y PDF se explica en
[Opciones y PDF del diario](docs/FASE2_OPCIONES_PDF.md).
La historia PDF y sus campos nuevos se explican en
[Historia Clínica FOR-SSS-04](docs/FASE2_HISTORIA_PDF.md).
El flujo de aprobación y conservación de constancias está en
[Constancia de Reposo FOR-SSS-07](docs/FASE2_REPOSO_PDF.md).

No uses la base SQLite versionada para pruebas. No reutilices los secretos
publicados anteriormente. No ejecutes `migrate` sobre una base con usuarios sin
seguir la secuencia de migraciones y administrador inicial documentada.
