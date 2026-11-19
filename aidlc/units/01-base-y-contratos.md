# Unit: Base y contratos

**Description:** Fija la estructura del código, los esquemas de los cuatro artefactos que pasan entre agentes y un módulo común para usar Bedrock y leer o escribir en `runs/`. Es la base que desbloquea el trabajo en paralelo.

**Bounded Context Rationale:** Es la frontera entre tres personas. Si los contratos cambian después, rompen a todos, por eso se fijan primero y por separado del resto.

**User Stories:**

- WHEN un agente termina su trabajo THE SYSTEM SHALL escribir su artefacto en `runs/<id>/` con el formato definido en `contratos-agentes.md`.
- WHEN un artefacto no cumple su esquema THE SYSTEM SHALL rechazarlo con un error que indique el campo faltante o inválido.
- WHEN un desarrollador ejecuta la comprobación de entorno THE SYSTEM SHALL confirmar que Bedrock responde con el modelo por defecto en la cuenta activa.
- IF el artefacto anterior no tiene aprobación `aprobado` THEN THE SYSTEM SHALL impedir que el agente siguiente lea ese artefacto como entrada.

**NFRs:**

- Entorno reproducible: un integrante nuevo lo instala con un solo comando documentado en el README.
- Sin credenciales ni IDs de cuenta fijos en el código.
- Validación de un artefacto: menos de 1 segundo.

**Risks:**

- Contratos demasiado rígidos o incompletos: mitigar con ejemplos reales del caso demo y revisión de los tres antes de hacer merge.
- Bedrock no habilitado en alguna cuenta: mitigar con la comprobación de entorno al inicio.

**Dependencies:** None (foundational unit)

**Suggested Bolts:**

- Bolt 1: Estructura de `src/`, `infra/`, `docs/` y entorno Python.
- Bolt 2: Esquemas y validadores de los cuatro artefactos con ejemplos.
- Bolt 3: Módulo común (cliente Bedrock, lectura y escritura en `runs/`) y comprobación de entorno.

## Implementation Reference

> **This section applies only after all units are defined, validated, and
> the HANDOFF phase is reached.** Ignore this section during decomposition.

When ready to implement this unit, create three implementation documents:

1. **`requirements.md`**: Full requirements using EARS notation
2. **`design.md`**: Technical design document
3. **`tasks.md`**: Implementation task breakdown with checkpoints

See the handoff reference for detailed instructions on each document.
