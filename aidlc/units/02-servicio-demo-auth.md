# Unit: Servicio demo auth-service

**Description:** Servicio sintético de autorizaciones de adquirencia, con reglas simples y datos ficticios. Es el objetivo sobre el que los agentes hacen el cambio de la demo.

**Bounded Context Rationale:** Es el sistema "de negocio" que el flujo modifica. Tiene su propio código, pruebas y ciclo de despliegue, independiente de los agentes.

**User Stories:**

- WHEN llega un `POST /authorize` válido THE SYSTEM SHALL responder `approved` y `response_code` según las reglas del servicio.
- WHEN el monto supera el límite simulado THE SYSTEM SHALL rechazar con un código de respuesta y un mensaje.
- IF la solicitud tiene campos faltantes o inválidos THEN THE SYSTEM SHALL responder con error 400 y el detalle del campo.
- THE SYSTEM SHALL usar únicamente `card_token` ficticio y nunca PAN ni CVV.

**NFRs:**

- Latencia de respuesta: menos de 500 ms en el caso normal.
- Cobertura de pruebas de las reglas de decisión: al menos 80 %.
- La lógica de reglas está separada del manejador HTTP para poder modificarla con facilidad.

**Risks:**

- Servicio demasiado complejo para modificarlo en la demo: mitigar manteniéndolo en un único módulo de reglas.
- Cambios de infraestructura que dependan del servicio: mitigar acordando con Sysops el formato del paquete a desplegar.

**Dependencies:** 01 Base y contratos

**Suggested Bolts:**

- Bolt 1: Módulo de reglas y pruebas unitarias.
- Bolt 2: Manejador Lambda y validación de entrada.
- Bolt 3: Archivo de ejemplo de solicitudes para pruebas manuales.

## Implementation Reference

> **This section applies only after all units are defined, validated, and
> the HANDOFF phase is reached.** Ignore this section during decomposition.

When ready to implement this unit, create three implementation documents:

1. **`requirements.md`**: Full requirements using EARS notation
2. **`design.md`**: Technical design document
3. **`tasks.md`**: Implementation task breakdown with checkpoints

See the handoff reference for detailed instructions on each document.
