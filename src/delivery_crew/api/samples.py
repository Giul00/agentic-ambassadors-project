"""Genera ejecuciones de ejemplo en distintos estados, para desarrollar y probar el panel.

Uso:  python -m delivery_crew.api.samples [carpeta]     (por defecto: runs)

Crea:
  demo-completo        las cuatro etapas aprobadas, con auditoría repartida en el tiempo
  demo-por-aprobar     requerimiento aprobado y diseño esperando al arquitecto
  demo-rechazado       diseño rechazado por el arquitecto
  demo-recien-creado   solo el requerimiento, sin aprobar
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .. import examples
from ..contracts import Approval
from ..runs import RunStore

_START = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _write_audit(store: RunStore, events: list[tuple[int, str, str, str | None]]) -> None:
    """events: (minutos desde el inicio, actor, acción, archivo)."""
    store.audit_path.unlink(missing_ok=True)
    lines = []
    for minutes, actor, action, artifact in events:
        entry = {"run_id": store.run_id, "at": (_START + timedelta(minutes=minutes)).isoformat(),
                 "actor": actor, "action": action}
        if artifact:
            entry["artifact"] = artifact
        lines.append(json.dumps(entry, ensure_ascii=False))
    store.audit_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _put(store: RunStore, artifact) -> None:
    store.write(artifact, actor="muestra")


def create_samples(base_dir: str | Path) -> list[str]:
    base = Path(base_dir)

    rid = "demo-completo"
    s = RunStore(rid, base).create()
    for art in (examples.requirement(rid), examples.design(rid), examples.change(rid), examples.deployment(rid)):
        _put(s, art)
    _write_audit(s, [
        (0, "orquestador", "run_created", None),
        (0, "orquestador", "artifact_written", "01-requerimiento.md"),
        (1, "arquitecto", "artifact_written", "02-diseno.md"),
        (2, "arquitecto", "approval_aprobado", "02-diseno.md"),
        (5, "desarrollador", "artifact_written", "03-cambio.md"),
        (6, "desarrollador", "approval_aprobado", "03-cambio.md"),
        (9, "sysops", "artifact_written", "04-despliegue.md"),
        (11, "sysops", "approval_aprobado", "04-despliegue.md"),
    ])

    rid = "demo-por-aprobar"
    s = RunStore(rid, base).create()
    _put(s, examples.requirement(rid))
    _put(s, examples.design(rid, approved=False))
    _write_audit(s, [
        (0, "orquestador", "run_created", None),
        (0, "orquestador", "artifact_written", "01-requerimiento.md"),
        (1, "arquitecto", "artifact_written", "02-diseno.md"),
    ])

    rid = "demo-rechazado"
    s = RunStore(rid, base).create()
    _put(s, examples.requirement(rid))
    rejected = examples.design(rid, approved=False)
    rejected.approval = Approval(status="rechazado", by="arquitecto", at=_START + timedelta(minutes=3),
                                 reason="Usa memoria de la Lambda; no cumple el estándar de estado compartido.")
    _put(s, rejected)
    _write_audit(s, [
        (0, "orquestador", "run_created", None),
        (0, "orquestador", "artifact_written", "01-requerimiento.md"),
        (1, "arquitecto", "artifact_written", "02-diseno.md"),
        (3, "arquitecto", "approval_rechazado", "02-diseno.md"),
    ])

    rid = "demo-recien-creado"
    s = RunStore(rid, base).create()
    _put(s, examples.requirement(rid, approved=False))
    _write_audit(s, [
        (0, "orquestador", "run_created", None),
        (0, "orquestador", "artifact_written", "01-requerimiento.md"),
    ])

    return ["demo-completo", "demo-por-aprobar", "demo-rechazado", "demo-recien-creado"]


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "runs")
    created = create_samples(target)
    print(f"Ejecuciones de ejemplo en {target}: {', '.join(created)}")
