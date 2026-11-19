# Unit: Orquestador y aprobaciones

**Description:** Coordina a los tres agentes en orden, detiene el flujo en cada compuerta de aprobación humana y registra una auditoría de cada decisión.

**Bounded Context Rationale:** Es el control del proceso, separado de la lógica de cada agente. Concentra las reglas de aprobación y auditoría, que son las que más importan en un entorno regulado.

**User Stories:**

- WHEN el usuario entrega un requerimiento THE SYSTEM SHALL crear una ejecución en `runs/<id>/` e iniciar el agente Arquitecto.
- WHEN un agente termina THE SYSTEM SHALL mostrar su artefacto y esperar la aprobación o el rechazo de la persona responsable.
- WHEN la persona aprueba THE SYSTEM SHALL registrar nombre y fecha en el artefacto y pasar al agente siguiente.
- IF la persona rechaza THEN THE SYSTEM SHALL detener el flujo y guardar el motivo.
- THE SYSTEM SHALL registrar cada traspaso, aprobación y error en `audit.jsonl`.

**NFRs:**

- Ningún agente corre sin la aprobación del artefacto anterior (verificable con una prueba).
- Cada línea de auditoría incluye identificador de ejecución, agente, acción y hora.
- El orquestador puede correr con agentes simulados para probarlo de forma aislada.

**Risks:**

- Aprobaciones que se pueden saltar: mitigar con una prueba que intente avanzar sin aprobación.
- Dependencia de las otras unidades para probar: mitigar con agentes simulados.

**Dependencies:** 01 Base y contratos

**Suggested Bolts:**

- Bolt 1: Flujo secuencial con agentes simulados.
- Bolt 2: Compuerta de aprobación por línea de comandos.
- Bolt 3: Registro de auditoría y manejo de rechazos.

## Implementation Reference

> **This section applies only after all units are defined, validated, and
> the HANDOFF phase is reached.** Ignore this section during decomposition.

When ready to implement this unit, create three implementation documents:

1. **`requirements.md`**: Full requirements using EARS notation
2. **`design.md`**: Technical design document
3. **`tasks.md`**: Implementation task breakdown with checkpoints

See the handoff reference for detailed instructions on each document.
