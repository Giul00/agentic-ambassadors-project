---
id: ARQ-06
titulo: Infraestructura parametrizada
---

# ARQ-06: Infraestructura parametrizada

**Regla:** El diseño no puede fijar un ID de cuenta AWS ni una región
dentro de la infraestructura propuesta. Cuenta y región se parametrizan.

**Por qué:** Cada integrante despliega en pruebas desde su propia cuenta
(`tech.md`); solo la presentación final va a la cuenta del arquitecto. Un
ID fijo rompe ese flujo para los otros dos.

**Cómo se verifica:** Si el diseño describe recursos de IaC (tablas,
roles, funciones), no debe incluir un número de cuenta de 12 dígitos ni
una región fija en el texto del diseño.

**Veredicto si se incumple:** `rechazado`.
