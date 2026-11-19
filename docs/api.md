# API del panel (para el front en React)

Servidor local, solo lectura y decisiones sobre las ejecuciones guardadas en `runs/`.

## Levantarla

```powershell
pip install -e ".[dev]"
python -m delivery_crew.api.samples runs        # crea 4 ejecuciones de ejemplo en distintos estados
python -m delivery_crew.api --port 8000         # http://127.0.0.1:8000
```

- Documentación interactiva (Swagger): http://127.0.0.1:8000/docs
- Carpeta de ejecuciones: `--runs-dir <ruta>` o variable `DELIVERY_CREW_RUNS_DIR`.
- CORS permitido por defecto: `http://localhost:5173` (Vite) y `http://localhost:3000`. Para otros orígenes, definir `DELIVERY_CREW_CORS` con una lista separada por comas.
- No tiene autenticación. Escucha solo en `127.0.0.1`; no la expongas a una red abierta.

## Endpoints

| Método | Ruta | Devuelve |
|---|---|---|
| GET | `/api/health` | `{"status":"ok","runs_dir":"runs"}` |
| GET | `/api/runs` | Lista de resúmenes de ejecuciones |
| GET | `/api/runs/{run_id}` | Detalle: etapas, artefactos y métricas |
| GET | `/api/runs/{run_id}/audit` | Registro de auditoría, en orden cronológico |
| POST | `/api/runs/{run_id}/stages/{step}/decision` | Aprueba o rechaza una etapa y devuelve el detalle actualizado |

`step` va de 1 a 4: 1 Requerimiento, 2 Diseño, 3 Cambio, 4 Despliegue.

## Estados

**Estado de una etapa** (`stages[].state`):

| Valor | Significado | Color sugerido |
|---|---|---|
| `esperando` | La etapa anterior todavía no está aprobada | gris |
| `en_curso` | Un agente está trabajando en esta etapa (aún no hay artefacto) | azul |
| `por_aprobar` | El artefacto existe y espera una decisión humana | amarillo |
| `aprobado` | Una persona lo aprobó | verde |
| `rechazado` | Una persona lo rechazó; el flujo se detiene | rojo |
| `invalido` | El archivo existe pero no cumple el contrato (ver `error`) | rojo oscuro |

**Estado general** (`state` de la ejecución): `en_curso`, `esperando_aprobacion`, `completo`, `rechazado`, `invalido`.

## Ejemplos

### GET /api/runs

```json
[
  {
    "run_id": "demo-por-aprobar",
    "state": "esperando_aprobacion",
    "started_at": "2026-01-01T12:00:00+00:00",
    "stages": [
      {"step": 1, "state": "aprobado"},
      {"step": 2, "state": "por_aprobar"},
      {"step": 3, "state": "esperando"},
      {"step": 4, "state": "esperando"}
    ]
  }
]
```

### GET /api/runs/{run_id}

```json
{
  "run_id": "demo-completo",
  "state": "completo",
  "stages": [
    {
      "step": 2,
      "key": "design",
      "label": "Diseño",
      "filename": "02-diseno.md",
      "state": "aprobado",
      "error": null,
      "artifact": {
        "run_id": "demo-completo",
        "created_at": "2026-01-01T12:00:00Z",
        "approval": {"status": "aprobado", "by": "arquitecto", "at": "2026-01-01T12:00:00Z", "reason": null},
        "summary": "Contar solicitudes por card_token en una tabla DynamoDB con TTL de 60 segundos.",
        "components": ["auth-service (reglas)", "DynamoDB: tabla de frecuencia"],
        "decision": "Usar DynamoDB con contador atómico y TTL en lugar de memoria de la Lambda.",
        "risks": ["Costo por escritura en cada solicitud.", "Latencia extra de una llamada a DynamoDB."],
        "verdict": "aprobado",
        "standards_cited": ["Permisos mínimos", "Sin datos de tarjeta reales"],
        "open_questions": []
      }
    }
  ],
  "metrics": {
    "elapsed_seconds": 660,
    "human_approvals": 4,
    "automated_steps_done": 3,
    "automated_steps_total": 3,
    "audit_events": 8
  }
}
```

(La lista `stages` real trae las cuatro etapas; aquí se muestra una por brevedad. Si una etapa aún no tiene archivo, `artifact` es `null`.)

Campos de `artifact` según la etapa (todos incluyen además `run_id`, `created_at`, `body` y `approval`):

| Etapa | Campos propios |
|---|---|
| 1 `requirement` | `title`, `description`, `acceptance_criteria[]`, `affected_service` |
| 2 `design` | `summary`, `components[]`, `decision`, `risks[]`, `verdict`, `standards_cited[]`, `open_questions[]`, `deployment_spec` (objeto o `null`) |
| 3 `change` | `branch`, `pull_request_url`, `files_modified[]`, `test_result`, `test_summary`, `deliverables[]` |
| 4 `deployment` | `target_account_id`, `region`, `resources[]`, `estimated_cost_usd`, `rollback_plan`, `health_check`, `rolled_back` |

### POST /api/runs/{run_id}/stages/{step}/decision

Aprobar:
```json
{"status": "aprobado", "by": "arquitecto"}
```

Rechazar (el motivo es obligatorio):
```json
{"status": "rechazado", "by": "arquitecto", "reason": "No cumple el estándar de estado compartido."}
```

Respuesta: el mismo objeto que `GET /api/runs/{run_id}`, ya actualizado.

### GET /api/runs/{run_id}/audit

```json
[
  {"run_id": "demo-completo", "at": "2026-01-01T12:00:00+00:00", "actor": "orchestrator", "action": "run_created"},
  {"run_id": "demo-completo", "at": "2026-01-01T12:02:00+00:00", "actor": "arquitecto", "action": "approval_aprobado", "artifact": "02-diseno.md"}
]
```

## Errores

| Código | Cuándo |
|---|---|
| 400 | Identificador de ejecución inválido |
| 404 | La ejecución no existe |
| 409 | La etapa no admite una decisión (no está `por_aprobar`, o ya se decidió) |
| 422 | Cuerpo inválido (falta `by`, estado desconocido, o rechazo sin `reason`) |

El detalle viene en `{"detail": "..."}`.

## Sugerencias para el front

- Refrescar cada 2 o 3 segundos con `GET /api/runs/{run_id}`. Los agentes escriben archivos, así que no hay notificaciones push.
- Mostrar los botones Aprobar y Rechazar solo cuando `state === "por_aprobar"`. El servidor lo valida igual.
- El tiempo manual de comparación no lo guarda la API. Defínelo como una constante o campo editable en el front y compáralo con `metrics.elapsed_seconds`.
- La API no entrega el diff del código. Para la etapa 3 se muestran `files_modified`, `test_summary` y el enlace `pull_request_url`.
