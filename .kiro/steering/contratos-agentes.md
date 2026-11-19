---
title: Contratos entre agentes
inclusion: always
priority: high
---

# Contratos entre agentes

Cada traspaso entre agentes es un artefacto en archivo, con un formato fijo. Así cada persona puede construir su agente por separado y luego integrarlos.

Los artefactos de cada ejecución viven en `runs/<id-ejecucion>/`.

## 1. Requerimiento (entrada del orquestador)
Archivo: `runs/<id>/01-requerimiento.md`
Campos: título, descripción, criterios de aceptación, servicio afectado.

## 2. Diseño (salida del agente Arquitecto)
Archivo: `runs/<id>/02-diseno.md`
 Campos: resumen, componentes afectados, decisión (ADR), riesgos, veredicto contra estándares (`aprobado` | `observaciones` | `rechazado`) y `deployment_spec`.
 `deployment_spec` declara ambiente, componentes tipados, dependencias, exposición de red, clasificación de datos, health check, rollback y observabilidad. Es obligatorio para que SysOps genere infraestructura.
Estado de aprobación humana: `pendiente` | `aprobado` | `rechazado`, con nombre y fecha.

## 3. Cambio de código (salida del agente Desarrollador)
Archivo: `runs/<id>/03-cambio.md`
 Campos: rama, enlace al pull request, archivos modificados, resultado de las pruebas y `deliverables`.
 Cada entregable declara el componente de Arquitectura que implementa, tipo de artefacto (`zip`, `container`, `static` o `package`), ruta fuente, comando de build y entrypoint cuando aplica.
Estado de aprobación humana: igual al anterior.

## 4. Plan de despliegue (salida del agente Despliegue)
Archivo: `runs/<id>/04-despliegue.md`
Campos: recursos a crear o modificar, costo estimado, plan de rollback, resultado del chequeo de salud.
Estado de aprobación humana: igual al anterior.

## Reglas
- Un agente solo avanza si el artefacto anterior tiene aprobación humana `aprobado`.
- Cada artefacto incluye el identificador de la ejecución y la fecha.
- Cambiar un contrato requiere acuerdo de los tres integrantes.
