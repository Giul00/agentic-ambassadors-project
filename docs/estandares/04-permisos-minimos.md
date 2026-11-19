---
id: ARQ-04
titulo: Permisos mínimos
---

# ARQ-04: Permisos mínimos

**Regla:** Cada componente (Lambda, agente, rol) recibe solo los permisos
IAM que necesita para su función. Nunca `Action: "*"` ni `Resource: "*"`
en una política nueva. Solo el agente de Despliegue puede modificar
infraestructura.

**Por qué:** Guardrail general del proyecto (`guardrails.md`, regla 4),
aplicado al diseño: si el diseño no acota los permisos explícitamente, el
agente de Despliegue termina otorgando de más "para que funcione".

**Cómo se verifica:** El diseño debe listar, para cada recurso nuevo, qué
componente lo usa y con qué acción concreta (ej. `dynamodb:GetItem`,
`dynamodb:PutItem` sobre la tabla puntual, no sobre `*`).

**Veredicto si se incumple:** `observaciones` si falta el detalle,
`rechazado` si propone permisos amplios explícitamente.
