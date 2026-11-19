"""Lógica del panel, sin web: estado de cada etapa, métricas y decisiones humanas.

Estados de una etapa:
  esperando    la etapa anterior aún no está aprobada
  en_curso     la etapa anterior está aprobada y este artefacto todavía no existe
  por_aprobar  el artefacto existe y espera una decisión humana
  aprobado     una persona lo aprobó
  rechazado    una persona lo rechazó (el flujo se detiene)
  invalido     el archivo existe pero no cumple el contrato
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ..contracts import ARTIFACTS, Artifact, ContractError
from ..runs import RunStore

LABELS = {1: "Requerimiento", 2: "Diseño", 3: "Cambio", 4: "Despliegue"}
KEYS = {1: "requirement", 2: "design", 3: "change", 4: "deployment"}
AUTOMATED_STEPS = (2, 3, 4)  # etapas que produce un agente


class DecisionError(Exception):
    """La decisión no se puede aplicar en el estado actual."""


@dataclass
class Stage:
    step: int
    state: str
    artifact: Artifact | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        cls = ARTIFACTS[self.step - 1]
        return {
            "step": self.step,
            "key": KEYS[self.step],
            "label": LABELS[self.step],
            "filename": cls.FILENAME,
            "state": self.state,
            "artifact": self.artifact.model_dump(mode="json") if self.artifact else None,
            "error": self.error,
        }


def list_run_ids(base_dir: str | Path) -> list[str]:
    base = Path(base_dir)
    if not base.is_dir():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir() and not p.name.startswith("."))


def run_exists(base_dir: str | Path, run_id: str) -> bool:
    return RunStore(run_id, base_dir).path.is_dir()


def load_stages(store: RunStore) -> list[Stage]:
    stages: list[Stage] = []
    previous_approved = True  # la etapa 1 la origina la persona usuaria
    for step, cls in enumerate(ARTIFACTS, start=1):
        if not store.exists(cls):
            stages.append(Stage(step, "en_curso" if previous_approved else "esperando"))
            previous_approved = False
            continue
        try:
            artifact = store.read(cls)
        except ContractError as exc:
            stages.append(Stage(step, "invalido", error=str(exc)))
            previous_approved = False
            continue
        status = artifact.approval.status
        state = {"aprobado": "aprobado", "rechazado": "rechazado"}.get(status, "por_aprobar")
        stages.append(Stage(step, state, artifact))
        previous_approved = status == "aprobado"
    return stages


def overall_state(stages: list[Stage]) -> str:
    states = [s.state for s in stages]
    if "rechazado" in states:
        return "rechazado"
    if "invalido" in states:
        return "invalido"
    if all(s == "aprobado" for s in states):
        return "completo"
    if "por_aprobar" in states:
        return "esperando_aprobacion"
    return "en_curso"


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def metrics(store: RunStore, stages: list[Stage]) -> dict[str, Any]:
    audit = store.read_audit()
    elapsed = None
    if len(audit) >= 2:
        elapsed = int((_parse(audit[-1]["at"]) - _parse(audit[0]["at"])).total_seconds())
    return {
        "elapsed_seconds": elapsed,
        "human_approvals": sum(1 for s in stages if s.state == "aprobado"),
        "automated_steps_done": sum(
            1 for s in stages if s.step in AUTOMATED_STEPS and s.artifact is not None
        ),
        "automated_steps_total": len(AUTOMATED_STEPS),
        "audit_events": len(audit),
    }


def summary(store: RunStore) -> dict[str, Any]:
    stages = load_stages(store)
    audit = store.read_audit()
    return {
        "run_id": store.run_id,
        "state": overall_state(stages),
        "started_at": audit[0]["at"] if audit else None,
        "stages": [{"step": s.step, "state": s.state} for s in stages],
    }


def detail(store: RunStore) -> dict[str, Any]:
    stages = load_stages(store)
    return {
        "run_id": store.run_id,
        "state": overall_state(stages),
        "stages": [s.to_dict() for s in stages],
        "metrics": metrics(store, stages),
    }


def decide(store: RunStore, step: int, status: str, by: str, reason: str | None) -> dict[str, Any]:
    if step not in LABELS:
        raise DecisionError(f"etapa inexistente: {step}")
    if status not in ("aprobado", "rechazado"):
        raise DecisionError("la decisión debe ser 'aprobado' o 'rechazado'")
    stage = load_stages(store)[step - 1]
    if stage.state != "por_aprobar":
        raise DecisionError(
            f"la etapa {step} ({LABELS[step]}) está '{stage.state}' y no admite una decisión"
        )
    store.decide(ARTIFACTS[step - 1], status, by=by, reason=reason)
    return detail(store)
