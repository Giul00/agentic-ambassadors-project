---
title: Guardrails de seguridad
inclusion: always
priority: high
---

# Guardrails

Estas reglas aplican a todo el código, los agentes y los comandos que se generen en este repositorio.

1. Prohibido manejar datos reales de tarjetas (PAN, CVV, pistas). Usar solo datos sintéticos.
2. Los secretos nunca van en el código, en archivos versionados ni en logs. Usar variables de entorno o Secrets Manager.
3. Ninguna acción de despliegue o cambio de infraestructura se ejecuta sin aprobación humana explícita.
4. Permisos mínimos: cada agente recibe solo los permisos que necesita. Solo el agente de Despliegue puede modificar infraestructura.
5. Acciones destructivas (borrar recursos, force push, borrar datos) requieren confirmación del usuario.
6. Cada decisión y traspaso entre agentes deja un registro de auditoría.
7. Las credenciales temporales del workshop no se suben al repositorio ni se pegan en documentos.
8. Validar toda entrada externa antes de usarla en comandos, consultas o plantillas.
