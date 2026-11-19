---
id: ARQ-03
titulo: Cifrado y datos transitorios
---

# ARQ-03: Cifrado y datos transitorios

**Regla:** El tráfico entre componentes usa TLS. Los datos persistentes
que son transitorios por naturaleza (contadores, marcas de tiempo de
control de frecuencia, nonces) se guardan con un TTL explícito, nunca sin
vencimiento.

**Por qué:** Minimiza la superficie de datos retenidos. Un contador de
frecuencia por `card_token` solo tiene sentido durante la ventana de
control (ej. 60 segundos); guardarlo indefinidamente es retención
innecesaria.

**Cómo se verifica:** Si el diseño agrega una tabla o estructura para
contar eventos por `card_token` u otro identificador, debe especificar un
TTL coherente con la ventana de la regla de negocio.

**Veredicto si se incumple:** `observaciones` (salvo que además incumpla
ARQ-01, en cuyo caso es `rechazado`).
