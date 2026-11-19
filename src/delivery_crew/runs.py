"""Lectura y escritura de artefactos en runs/<id>/, con compuerta de aprobación y auditoría."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TypeVar

from .contracts import BY_STEP, Approval, Artifact, ContractError, utcnow

A = TypeVar("A", bound=Artifact)

_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class NotApprovedError(PermissionError):
    """El artefacto anterior no tiene aprobación humana 'aprobado'."""


class RunStore:
    """Una ejecución del flujo. Guarda los artefactos y el registro de auditoría."""

    def __init__(self, run_id: str, base_dir: str | Path = "runs") -> None:
        # Validar el id evita rutas como "../x" que escriban fuera de runs/.
        if not _RUN_ID.fullmatch(run_id) or ".." in run_id:
            raise ValueError(f"run_id inválido: {run_id!r}")
        self.run_id = run_id
        self.path = Path(base_dir) / run_id

    def create(self) -> "RunStore":
        self.path.mkdir(parents=True, exist_ok=True)
        self.audit("orchestrator", "run_created")
        return self

    # --- artefactos ---------------------------------------------------------

    def write(self, artifact: Artifact, actor: str = "unknown") -> Path:
        if artifact.run_id != self.run_id:
            raise ContractError(
                f"el artefacto es de la ejecución {artifact.run_id!r}, no de {self.run_id!r}"
            )
        self.path.mkdir(parents=True, exist_ok=True)
        target = self.path / artifact.FILENAME
        target.write_text(artifact.to_markdown(), encoding="utf-8")
        self.audit(actor, "artifact_written", artifact=artifact.FILENAME,
                   approval=artifact.approval.status)
        return target

    def read(self, cls: type[A]) -> A:
        target = self.path / cls.FILENAME
        if not target.exists():
            raise FileNotFoundError(f"no existe {target}")
        return cls.from_markdown(target.read_text(encoding="utf-8"))  # type: ignore[return-value]

    def exists(self, cls: type[Artifact]) -> bool:
        return (self.path / cls.FILENAME).exists()

    def read_input_for(self, step: int, cls: type[A]) -> A:
        """Lee el artefacto del paso anterior. Falla si no está aprobado por una persona."""
        if step - 1 not in BY_STEP:
            raise ValueError(f"el paso {step} no tiene paso anterior")
        previous = self.read(BY_STEP[step - 1])
        if previous.approval.status != "aprobado":
            raise NotApprovedError(
                f"{previous.FILENAME} está '{previous.approval.status}'; "
                f"se necesita 'aprobado' para continuar con el paso {step}"
            )
        return self.read(cls)

    def decide(self, cls: type[Artifact], status: str, by: str, reason: str | None = None) -> Artifact:
        """Registra la aprobación o el rechazo humano de un artefacto."""
        artifact = self.read(cls)
        artifact.approval = Approval(status=status, by=by, at=utcnow(), reason=reason)  # type: ignore[arg-type]
        self.write(artifact, actor=by)
        self.audit(by, f"approval_{status}", artifact=cls.FILENAME, reason=reason)
        return artifact

    # --- auditoría ----------------------------------------------------------

    @property
    def audit_path(self) -> Path:
        return self.path / "audit.jsonl"

    def audit(self, actor: str, action: str, **details: object) -> None:
        self.path.mkdir(parents=True, exist_ok=True)
        entry = {"run_id": self.run_id, "at": utcnow().isoformat(), "actor": actor,
                 "action": action, **{k: v for k, v in details.items() if v is not None}}
        with self.audit_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def read_audit(self) -> list[dict]:
        if not self.audit_path.exists():
            return []
        return [json.loads(line) for line in self.audit_path.read_text(encoding="utf-8").splitlines() if line]
