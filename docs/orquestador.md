# Orquestador (unidad 06)

Corre el flujo completo sobre una ejecución en `runs/<id>/`:

```
Requerimiento ──> Arquitecto ──[aprobación]──> Desarrollador ──[aprobación]──> Despliegue ──[aprobación]──> completo
```

Es reanudable: en cada paso mira qué artefactos hay y en qué estado, y hace lo único que corresponde. Si se corta (Ctrl+C, error, credenciales vencidas), `resume` sigue desde donde quedó sin repetir lo hecho.

## Demo en dos terminales

Requiere credenciales AWS en el entorno (Bedrock) y el entorno Python instalado.

**Terminal 1: panel** (ver `panel/README.md`): API en el puerto 8000 y `npm run dev` en `panel/`.

**Terminal 2: orquestador**

```powershell
.\.venv\Scripts\python.exe -m delivery_crew.orchestrator start --run-id demo-vivo --example --by tomas --target-account 123456789012
```

El orquestador corre el Arquitecto y se queda esperando. En el panel aparece la ejecución con el diseño **por aprobar**: al aprobarlo, el orquestador lo detecta (relee cada 2 s) y corre el Desarrollador, y así hasta el final.

Para decidir en la terminal en lugar del panel, agregar `--interactive`.

## Comandos

| Comando | Qué hace |
|---|---|
| `start --example --by <nombre> --target-account <12 dígitos>` | Crea la ejecución con el requerimiento del caso demo y corre el flujo |
| `start --title ... --description ... --criterion ... [--criterion ...]` | Igual, con un requerimiento propio |
| `resume --run-id <id> --target-account <...>` | Continúa una ejecución |
| `resume --run-id <id> --retry-rejected` | Si el cambio de código fue rechazado, el Desarrollador lo rehace con el motivo |
| `status --run-id <id>` | Estado de cada etapa |

Opciones: `--interactive` (decidir en terminal), `--no-wait` (salir al quedar pendiente), `--poll <s>`, `--runs-dir`, `--repo`, `--region`.

## Cuándo se detiene

| Resultado | Cuándo |
|---|---|
| completo | Las cuatro etapas están aprobadas |
| esperando | Hay un artefacto por aprobar y se usó `--no-wait` |
| rechazado | Una persona rechazó una etapa (el motivo queda en el artefacto) |
| bloqueado | Una persona aprobó un diseño con veredicto distinto de `aprobado`, o un cambio con pruebas fallidas |
| inválido | Un artefacto no cumple el contrato |
| falló | Un agente lanzó un error; se corrige la causa y se hace `resume` |

Cada paso queda en `runs/<id>/audit.jsonl` (`stage_started`, `stage_finished`, `waiting_approval`, `stage_failed`, `flow_completed`, `flow_stopped`).

## Alcance

- El requerimiento lo aprueba quien lo crea (`--by`), al crearlo.
- La etapa 4 genera el plan y el bundle de despliegue; no ejecuta `cloudformation deploy` (lo hace el pipeline de SysOps tras su aprobación).
- Solo el cambio de código se reintenta con feedback. Un diseño rechazado detiene el flujo: se corrige el requerimiento y se crea una ejecución nueva.
