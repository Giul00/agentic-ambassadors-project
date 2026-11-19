---
title: Producto Delivery Crew
inclusion: always
priority: high
---

# Producto: Delivery Crew (adquirencia)

## Problema
Llevar un cambio de idea a producción en adquirencia implica esperas manuales: revisión de arquitectura, desarrollo, revisión de seguridad y despliegue. Cada una tiene su responsable y sus errores. Eso alarga el lead time y aumenta los fallos en producción.

## Objetivo
Reducir el tiempo de idea a producción manteniendo los controles de un entorno regulado: aprobación humana, trazabilidad y ausencia de datos sensibles.

## Usuarios
- Desarrollador: pide y recibe código y pruebas.
- Arquitecto: aprueba el diseño y las excepciones a estándares.
- Sysops: aprueba el despliegue y atiende el rollback.

## Alcance del MVP
Incluye: un flujo completo para un único caso, de requerimiento a despliegue verificado en la cuenta del workshop.
No incluye: sistemas productivos reales, datos reales de tarjetas, múltiples repositorios ni múltiples entornos.

## Agentes
| Agente | Entrada | Salida |
|---|---|---|
| Orquestador | Requerimiento en texto | Estado del flujo y traspasos |
| Arquitecto | Requerimiento | Diseño, ADR, diagrama y veredicto contra estándares |
| Desarrollador | Diseño aprobado | Código, pruebas y pull request |
| Despliegue | Pull request aprobado | IaC, despliegue, chequeo de salud y rollback |

## Flujo y aprobaciones humanas
1. El requerimiento entra al orquestador.
2. El agente Arquitecto propone el diseño. Aprueba el arquitecto.
3. El agente Desarrollador genera código y pruebas. Aprueba el desarrollador en el pull request.
4. El agente Despliegue prepara el cambio. Aprueba sysops.
5. Despliegue, verificación y reporte. Si falla, rollback.

## Caso demo (propuesto, ver `docs/caso-demo.md`)
Agregar el código de rechazo 65 (límite de frecuencia: más de 3 solicitudes en 60 segundos por `card_token`) a `auth-service`, un servicio sintético de autorizaciones. Detalle, guion y plan B en `docs/caso-demo.md`.

## Métricas de éxito
- Tiempo de la demo contra un estimado manual del mismo cambio.
- Pasos manuales eliminados.
- Defectos detectados antes de desplegar.
- Rollback exitoso ante un fallo provocado a propósito.

## Decisiones pendientes
1. Plazo y fecha de entrega.
2. Criterios de evaluación del hackathon.
3. ~~Servicio de ejemplo para la demo~~ Propuesto: `auth-service`. Falta que el equipo lo confirme.
4. Modelos de Bedrock: resuelto, ver tech.md (falta repetir la verificación en las otras dos cuentas).
5. ~~Cuenta AWS de despliegue~~ Resuelto: la cuenta del arquitecto de soluciones. Falta confirmar su ID y que tenga Bedrock habilitado.

## Documentos relacionados
- Arquitectura y diagramas: `docs/arquitectura.md`.
- Caso demo y guion: `docs/caso-demo.md`.
- Plan de trabajo y unidades: `aidlc/plan.md` y `aidlc/units/`.
- Supuestos pendientes de confirmar: `aidlc/elaboration-log.md`.
