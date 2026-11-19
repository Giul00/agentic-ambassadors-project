# Unit: Agente Despliegue e infraestructura

**Description:** Infraestructura como código del servicio demo y un agente que prepara el plan de despliegue, despliega, verifica la salud y revierte si falla.

**Bounded Context Rationale:** Es el único con permisos para modificar infraestructura. Tiene su propio ciclo (cuentas, permisos, costos) y lo mantiene sysops.

**User Stories:**

- WHEN recibe un `03-cambio.md` con aprobación `aprobado` THE SYSTEM SHALL generar `04-despliegue.md` con los recursos afectados, el costo estimado y el plan de rollback.
- WHEN sysops aprueba el plan THE SYSTEM SHALL desplegar en la cuenta activa y registrar el resultado.
- WHEN termina el despliegue THE SYSTEM SHALL ejecutar una verificación de salud sobre el servicio.
- IF la verificación falla THEN THE SYSTEM SHALL revertir al estado anterior y reportar la causa.
- IF la cuenta activa no coincide con la cuenta de despliegue acordada THEN THE SYSTEM SHALL detenerse sin desplegar.

**NFRs:**

- La infraestructura está parametrizada por cuenta y región, sin IDs fijos.
- Despliegue y verificación del caso demo en menos de 10 minutos.
- Permisos mínimos: el agente no puede borrar recursos ajenos al proyecto.

**Risks:**

- Rol del workshop sin permisos para algún recurso: mitigar probando un despliegue mínimo en la cuenta del arquitecto cuanto antes.
- Rollback que deja recursos huérfanos: mitigar con etiquetas del proyecto y prueba del rollback en la unidad 07.

**Dependencies:** 01 Base y contratos

**Suggested Bolts:**

- Bolt 1: Proyecto CDK del servicio demo, parametrizado.
- Bolt 2: Agente que produce el plan y el costo estimado.
- Bolt 3: Despliegue, verificación de salud y rollback.

## Implementation Reference

> **This section applies only after all units are defined, validated, and
> the HANDOFF phase is reached.** Ignore this section during decomposition.

When ready to implement this unit, create three implementation documents:

1. **`requirements.md`**: Full requirements using EARS notation
2. **`design.md`**: Technical design document
3. **`tasks.md`**: Implementation task breakdown with checkpoints

See the handoff reference for detailed instructions on each document.
