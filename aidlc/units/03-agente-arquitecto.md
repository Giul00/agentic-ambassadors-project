# Unit: Agente Arquitecto

**Description:** Agente que recibe un requerimiento y produce un diseño con ADR, diagrama y veredicto contra los estándares de arquitectura.

**Bounded Context Rationale:** Su conocimiento (estándares) y su salida (diseño) son propios de la arquitectura y los mantiene el arquitecto, con un ritmo de cambio distinto al del código.

**User Stories:**

- WHEN recibe `01-requerimiento.md` THE SYSTEM SHALL generar `02-diseno.md` con resumen, componentes afectados, decisión, riesgos y veredicto.
- WHEN el diseño incumple un estándar THE SYSTEM SHALL marcar el veredicto como `observaciones` o `rechazado` e indicar qué estándar y por qué.
- WHEN genera el diseño THE SYSTEM SHALL incluir un diagrama en Mermaid.
- IF el requerimiento es ambiguo o incompleto THEN THE SYSTEM SHALL listar las preguntas pendientes en lugar de inventar un diseño.

**NFRs:**

- Generación del diseño: menos de 60 segundos por requerimiento.
- Todo veredicto cita el estándar aplicado.
- La base de estándares es un conjunto de archivos Markdown que se edita sin tocar código.

**Risks:**

- El modelo aprueba diseños que incumplen: mitigar con un caso de prueba de incumplimiento forzado y aprobación humana siempre.
- Estándares demasiado genéricos: mitigar con 5 a 8 reglas concretas relevantes a pagos (datos de tarjetas, secretos, cifrado, permisos mínimos).

**Dependencies:** 01 Base y contratos

**Suggested Bolts:**

- Bolt 1: Base de estándares en Markdown.
- Bolt 2: Agente y prompt que producen `02-diseno.md`.
- Bolt 3: Casos de prueba: diseño válido y diseño con incumplimiento forzado.

## Implementation Reference

> **This section applies only after all units are defined, validated, and
> the HANDOFF phase is reached.** Ignore this section during decomposition.

When ready to implement this unit, create three implementation documents:

1. **`requirements.md`**: Full requirements using EARS notation
2. **`design.md`**: Technical design document
3. **`tasks.md`**: Implementation task breakdown with checkpoints

See the handoff reference for detailed instructions on each document.
