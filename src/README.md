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
| `delivery_crew/api/` | API del panel (FastAPI): `service.py` (lógica), `app.py` (rutas), `samples.py` (ejecuciones de ejemplo). Ver `docs/api.md`. |

| `delivery_crew/agents/developer.py` | Agente Desarrollador (Strands + Bedrock). Implementa un diseño aprobado en `services/auth_service` dentro de una copia aislada (`.worktrees/<run_id>`), verifica las pruebas, reintenta hasta 3 veces y escribe `03-cambio.md` con el diff. |
| `delivery_crew/agents/sandbox.py` | Herramientas acotadas del agente: listar, leer y escribir solo dentro del servicio, y correr sus pruebas sin credenciales AWS. |

El servicio demo está en `services/auth_service/` (ver su README). Pendiente: agente Arquitecto, agente Despliegue y orquestador.

## Agente Desarrollador

```powershell
# Requiere credenciales AWS en el entorno (Bedrock).
python -m delivery_crew.agents.developer --run-id demo-dev --seed     # crea requerimiento y diseño de ejemplo aprobados
python -m delivery_crew.agents.developer --run-id demo-dev --fresh    # repetir; si el cambio anterior fue rechazado, el agente recibe el motivo
```

- El resultado queda en `runs/<run_id>/03-cambio.md` como `por_aprobar`. Se aprueba o rechaza desde el panel.
- El commit queda en la rama local `agente/<run_id>`, con autor "Agente Desarrollador". Con `--push` se sube a `origin` si las pruebas pasan.
- Si se rechaza con un motivo y se repite con `--fresh`, el motivo entra en las instrucciones del agente.

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
