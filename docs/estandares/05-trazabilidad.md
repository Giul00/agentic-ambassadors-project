---
id: ARQ-05
titulo: Trazabilidad del diseño
---

# ARQ-05: Trazabilidad del diseño

**Regla:** Toda decisión de diseño que cree o modifique un recurso con
datos o permisos nuevos debe quedar en el ADR con: la decisión tomada, al
menos una alternativa considerada y por qué se descartó, y los riesgos
identificados.

**Por qué:** El ADR es el único registro de por qué el sistema quedó así.
Sin alternativas documentadas, una revisión futura no puede saber si la
decisión fue deliberada o un atajo.

**Cómo se verifica:** El campo `decision` del diseño no puede ser una
frase genérica sin alternativa descartada ni razón.

**Veredicto si se incumple:** `observaciones`.
