# Unit: Panel de control

**Description:** Interfaz visual para la presentación. Muestra el avance de una ejecución por etapas, el contenido de cada artefacto, las compuertas de aprobación humana con sus botones, la auditoría y las métricas. Consta de una API local (FastAPI) sobre `RunStore` y un front en React.

**Bounded Context Rationale:** Es la capa de presentación. No contiene lógica de los agentes: solo lee `runs/` y registra decisiones humanas a través de `RunStore.decide`. Puede desarrollarse con datos de ejemplo sin esperar a las otras unidades.

**User Stories:**

- WHEN la persona abre el panel THE SYSTEM SHALL listar las ejecuciones con su estado general y el estado de cada etapa.
- WHEN selecciona una ejecución THE SYSTEM SHALL mostrar las cuatro etapas, el artefacto de cada una y las métricas.
- WHEN una etapa está `por_aprobar` THE SYSTEM SHALL mostrar los botones Aprobar y Rechazar.
- WHEN la persona aprueba o rechaza THE SYSTEM SHALL registrar quién decidió y cuándo, y reflejar el nuevo estado.
- IF la persona rechaza sin indicar el motivo THEN THE SYSTEM SHALL impedir el envío.
- IF una etapa no está `por_aprobar` THEN THE SYSTEM SHALL rechazar la decisión con un error 409.
- WHEN un archivo no cumple el contrato THE SYSTEM SHALL mostrar la etapa como `invalido` con el detalle, sin fallar.

**NFRs:**

- La pantalla refleja un cambio en `runs/` en menos de 3 segundos.
- La API solo escucha en `127.0.0.1` y no expone rutas fuera de `runs/`.
- Funciona sin conexión a internet ni a AWS (se presenta desde una laptop).
- Legible proyectada: tipografía grande y estados distinguibles por texto y no solo por color.

**Risks:**

- El front consume mucho tiempo y desplaza otras unidades: mitigar con la API y datos de ejemplo ya listos, y un alcance mínimo (una pantalla).
- Cualquiera con acceso a la red local podría aprobar: mitigar escuchando solo en `127.0.0.1`.
- El panel muestra un estado distinto al real si los agentes escriben a mitad de lectura: mitigar con refresco periódico y manejo del estado `invalido`.

**Dependencies:** 01 Base y contratos

**Suggested Bolts:**

- Bolt 1: API y datos de ejemplo (hecho, ver `docs/api.md`).
- Bolt 2: Front: lista de ejecuciones y vista de pipeline por etapas.
- Bolt 3: Front: detalle de artefactos, aprobación y rechazo, auditoría.
- Bolt 4: Front: métricas, comparación con el tiempo manual y pulido para proyectar.

## Implementation Reference

> **This section applies only after all units are defined, validated, and
> the HANDOFF phase is reached.** Ignore this section during decomposition.

When ready to implement this unit, create three implementation documents:

1. **`requirements.md`**: Full requirements using EARS notation
2. **`design.md`**: Technical design document
3. **`tasks.md`**: Implementation task breakdown with checkpoints

See the handoff reference for detailed instructions on each document.
