---
id: ARQ-01
titulo: Datos de tarjetas
---

# ARQ-01: Datos de tarjetas

**Regla:** Ningún componente del diseño puede almacenar, loguear ni
transmitir PAN, CVV ni pista completa (track 1/2), ni en texto plano ni
cifrados "por si acaso". Solo se permiten identificadores sintéticos
(`card_token`) sin relación reversible con una tarjeta real.

**Por qué:** Es la regla central de un entorno de adquirencia regulado.
Guardar un dato real, aunque sea temporalmente, convierte cualquier
componente en alcance de cumplimiento de datos de tarjetas.

**Cómo se verifica:** El diseño no debe proponer guardar, cachear o
loguear el campo `card_token` original junto a información que permita
reconstruir un PAN, ni ningún campo adicional de tarjeta (número, CVV,
fecha de vencimiento).

**Veredicto si se incumple:** `rechazado`.
