# Unit: Agente Desarrollador

**Description:** Agente que toma un diseño aprobado y lo implementa sobre `auth-service`, con pruebas y un pull request.

**Bounded Context Rationale:** Es el único agente que modifica código de aplicación. Necesita acceso a archivos, pruebas y Git, y sus permisos deben ser distintos de los del agente de Despliegue.

**User Stories:**

- WHEN recibe un `02-diseno.md` con aprobación `aprobado` THE SYSTEM SHALL modificar el código del servicio y agregar o actualizar pruebas.
- WHEN termina los cambios THE SYSTEM SHALL ejecutar las pruebas y registrar el resultado en `03-cambio.md`.
- WHEN las pruebas pasan THE SYSTEM SHALL abrir un pull request y registrar su enlace.
- IF las pruebas fallan THEN THE SYSTEM SHALL intentar corregir hasta 2 veces y, si persiste, reportar el fallo sin abrir el pull request.
- THE SYSTEM SHALL limitar sus escrituras a la carpeta del servicio y a sus pruebas.

**NFRs:**

- Cambio del caso demo generado en menos de 3 minutos.
- No debe leer ni escribir secretos ni credenciales.
- Todo cambio queda en una rama propia, nunca en `main`.

**Risks:**

- Cambios fuera del alcance del diseño: mitigar limitando las rutas de escritura y mostrando el diff antes de aprobar.
- Pruebas que pasan sin verificar el requerimiento: mitigar exigiendo una prueba por criterio de aceptación.

**Dependencies:** 01 Base y contratos, 02 Servicio demo auth-service

**Suggested Bolts:**

- Bolt 1: Herramientas del agente (archivos acotados, ejecución de pruebas, Git).
- Bolt 2: Agente y prompt que implementan el diseño.
- Bolt 3: Apertura del pull request y escritura de `03-cambio.md`.

## Implementation Reference

> **This section applies only after all units are defined, validated, and
> the HANDOFF phase is reached.** Ignore this section during decomposition.

When ready to implement this unit, create three implementation documents:

1. **`requirements.md`**: Full requirements using EARS notation
2. **`design.md`**: Technical design document
3. **`tasks.md`**: Implementation task breakdown with checkpoints

See the handoff reference for detailed instructions on each document.
