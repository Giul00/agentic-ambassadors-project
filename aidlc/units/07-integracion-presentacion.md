# Unit: Integración y presentación

**Description:** Ejecuta el caso demo de punta a punta con los agentes reales en la cuenta del arquitecto, mide el beneficio y deja lista la presentación.

**Bounded Context Rationale:** Reúne el trabajo de los tres. Es donde se detectan los desajustes entre contratos y donde se prepara lo que se muestra al jurado.

**User Stories:**

- WHEN el equipo ejecuta el caso demo THE SYSTEM SHALL recorrer los cuatro pasos con las tres aprobaciones y dejar el servicio desplegado en la cuenta del arquitecto.
- WHEN el servicio desplegado recibe 4 solicitudes seguidas con el mismo `card_token` THE SYSTEM SHALL devolver el código `65` en la cuarta.
- WHEN se provoca un fallo a propósito THE SYSTEM SHALL revertir y reportar la causa.
- THE SYSTEM SHALL registrar el tiempo total y la cantidad de pasos manuales eliminados.

**NFRs:**

- La demo completa dura menos de 5 minutos.
- Existe un plan B: ejecución grabada y artefactos de `runs/`.
- La ejecución se repite al menos 2 veces sin intervención del equipo fuera de las aprobaciones.

**Risks:**

- Credenciales caducadas o permisos faltantes el día de la presentación: mitigar renovándolas antes y ensayando en la cuenta de despliegue.
- Dependencia de la red o de Bedrock en vivo: mitigar con el plan B grabado.

**Dependencies:** 02, 03, 04, 05, 06, 08

**Suggested Bolts:**

- Bolt 1: Ejecución completa en la cuenta del arquitecto.
- Bolt 2: Fallo provocado, rollback y medición de tiempos.
- Bolt 3: Guion, diapositivas y ensayo.

## Implementation Reference

> **This section applies only after all units are defined, validated, and
> the HANDOFF phase is reached.** Ignore this section during decomposition.

When ready to implement this unit, create three implementation documents:

1. **`requirements.md`**: Full requirements using EARS notation
2. **`design.md`**: Technical design document
3. **`tasks.md`**: Implementation task breakdown with checkpoints

See the handoff reference for detailed instructions on each document.
