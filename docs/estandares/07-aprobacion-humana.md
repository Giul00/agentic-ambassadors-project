---
id: ARQ-07
titulo: Aprobación humana bloqueante
---

# ARQ-07: Aprobación humana bloqueante

**Regla:** El diseño no puede asumir ni describir que algún paso del
flujo (diseño, cambio de código, despliegue) se ejecuta automáticamente
sin aprobación humana explícita.

**Por qué:** Es la regla central del flujo (`contratos-agentes.md`,
`guardrails.md` regla 3): cada traspaso queda bloqueado hasta que una
persona aprueba.

**Cómo se verifica:** El diseño no debe proponer saltarse la aprobación
de arquitecto, desarrollador o sysops para "ganar tiempo en la demo".

**Veredicto si se incumple:** `rechazado`.
