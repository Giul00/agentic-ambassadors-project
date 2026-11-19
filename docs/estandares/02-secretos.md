---
id: ARQ-02
titulo: Secretos
---

# ARQ-02: Secretos

**Regla:** Ningún secreto (credenciales, API keys, tokens de larga
duración) va en código, en archivos versionados, en logs ni en artefactos
de `runs/`. Se usan variables de entorno o AWS Secrets Manager.

**Por qué:** Los artefactos entre agentes viajan por Git (decisión de
arquitectura). Cualquier secreto que caiga ahí queda expuesto en el
historial, aunque se borre después.

**Cómo se verifica:** El diseño no debe proponer pasar secretos como
parámetro de CLI, variable en un archivo de configuración versionado, ni
incluirlos en el cuerpo de un artefacto Markdown.

**Veredicto si se incumple:** `rechazado`.
