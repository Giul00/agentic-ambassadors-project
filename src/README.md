# src

Código del proyecto. Paquete Python `delivery_crew` (Python 3.11 o superior).

## Módulos

| Módulo | Qué hace |
|---|---|
| `delivery_crew/contracts.py` | Modelos Pydantic de los cuatro artefactos entre agentes (`Requirement`, `Design`, `Change`, `Deployment`) y de la aprobación humana. Convierte a y desde Markdown con YAML. |
| `delivery_crew/runs.py` | `RunStore`: lee y escribe artefactos en `runs/<id>/`, bloquea el paso siguiente si el anterior no está `aprobado` y registra la auditoría en `audit.jsonl`. |
| `delivery_crew/bedrock.py` | Modelo y región de Bedrock (por entorno, sin IDs de cuenta). `get_strands_model()` para crear agentes de Strands. |
| `delivery_crew/check_env.py` | Comprobación de entorno en la cuenta activa. |
| `delivery_crew/examples.py` | Artefactos de ejemplo del caso demo. |

Pendiente (otras unidades): `agents/`, `orchestrator/` y `auth_service/`.

## Uso rápido

```python
from delivery_crew.runs import RunStore
from delivery_crew.contracts import Requirement, Design

store = RunStore("demo-0002").create()
store.write(Requirement(run_id="demo-0002", title="...", description="...",
                        acceptance_criteria=["..."], affected_service="auth-service"),
            actor="orquestador")
store.decide(Requirement, "aprobado", by="tomas")          # aprobación humana
req = store.read_input_for(2, Requirement)                  # falla si no está aprobado
```

Ejemplos reales de cada artefacto en `docs/ejemplos/demo-0001/`.
