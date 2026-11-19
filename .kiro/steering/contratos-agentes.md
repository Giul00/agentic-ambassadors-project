---
title: Contratos entre agentes
inclusion: always
priority: high
---

# Contratos entre agentes

Cada traspaso entre agentes es un artefacto en archivo, con un formato fijo. Así cada persona puede construir su agente por separado y luego integrarlos.

Los artefactos de cada ejecución viven en `runs/<id-ejecucion>/`. Los modelos están en `src/delivery_crew/contracts.py` y las convenciones de nombres en `src/delivery_crew/conventions.py`.

## 1. Requerimiento (entrada del orquestador)
Archivo: `runs/<id>/01-requerimiento.md`
Campos: título, descripción, criterios de aceptación, servicio afectado.

## 2. Diseño (salida del agente Arquitecto)
Archivo: `runs/<id>/02-diseno.md`
Campos: resumen, componentes afectados, decisión (ADR), riesgos, veredicto contra estándares (`aprobado` | `observaciones` | `rechazado`) y `deployment_spec`.
`deployment_spec` declara ambiente, componentes tipados, dependencias, exposición de red, clasificación de datos, health check, rollback y observabilidad. Es obligatorio para que SysOps genere infraestructura.
Estado de aprobación humana: `pendiente` | `aprobado` | `rechazado`, con nombre y fecha.

### Configuración de componentes (`configuration`)
Arquitectura fija aquí los nombres que el código y la infraestructura deben compartir. Es la única fuente de esos valores: el agente Desarrollador los recibe como requisito obligatorio y el agente Despliegue los traduce a parámetros de la plantilla.

| Tipo (`kind`) | Clave | Significado | Ejemplo |
|---|---|---|---|
| `dynamodb` | `partition_key` | Atributo clave de partición (String) | `pk` |
| `dynamodb` | `ttl_attribute` | Atributo TTL (Number, epoch en segundos) | `ttl` |
| `lambda` | `FREQUENCY_STORE` | Variable de entorno del contador: `dynamodb` en AWS, `memory` en pruebas | `dynamodb` |

- El contrato rechaza claves no listadas para `dynamodb` y `lambda`, y valores con caracteres fuera de `A-Z a-z 0-9 _ . -`.
- El agente Despliegue falla si una clave no tiene parámetro en la plantilla, en lugar de ignorarla.
- La infraestructura siempre inyecta el nombre de la tabla en la variable `FREQUENCY_TABLE_NAME`.

## 3. Cambio de código (salida del agente Desarrollador)
Archivo: `runs/<id>/03-cambio.md`
Campos: rama, enlace al pull request, archivos modificados, resultado de las pruebas y `deliverables`.
Cada entregable declara el componente de Arquitectura que implementa, tipo de artefacto (`zip`, `container`, `static` o `package`), ruta fuente, comando de build y entrypoint cuando aplica.
- El agente Desarrollador genera un entregable por cada componente `lambda` del `deployment_spec`, con valores fijos: `services/auth_service`, entrypoint `auth_service.handler.lambda_handler`.
- `build_command` es informativo. El pipeline usa un empaquetado fijo y nunca ejecuta un comando tomado de un artefacto.
- El agente Despliegue rechaza entregables cuya ruta no exista en el repositorio.
Estado de aprobación humana: igual al anterior.

## 4. Plan de despliegue (salida del agente Despliegue)
Archivo: `runs/<id>/04-despliegue.md`
Campos: recursos a crear o modificar, costo estimado, plan de rollback, resultado del chequeo de salud.
El bundle generado (`runs/<id>/generated/`) incluye en `manifest.yml` los `parameter_overrides` aplicados a la plantilla.
Estado de aprobación humana: igual al anterior.

## Reglas
- Un agente solo avanza si el artefacto anterior tiene aprobación humana `aprobado`.
- Cada artefacto incluye el identificador de la ejecución y la fecha.
- Cambiar un contrato o una convención requiere acuerdo de los tres integrantes.
