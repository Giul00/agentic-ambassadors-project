"""Ejecuta el orquestador en segundo plano para las ejecuciones lanzadas desde el panel.

Cada ejecución tiene a lo sumo un hilo activo. El hilo espera las aprobaciones humanas
leyendo runs/<id>/ (las decisiones llegan por la API), así que el panel solo decide y mira.
Si la API se reinicia, los hilos se pierden: la ejecución se retoma con "Reanudar".
"""

from __future__ import annotations

import threading
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .. import orchestrator as orch
from ..runs import RunStore

AgentsFactory = Callable[[], orch.Agents]

WAIT_TIMEOUT_SECONDS = 2 * 60 * 60  # un hilo no espera aprobaciones más de 2 horas
POLL_SECONDS = 1.5


class RunnerBusy(RuntimeError):
    """La ejecución ya tiene el orquestador corriendo."""


@dataclass
class RunnerState:
    run_id: str
    active: bool = True
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).replace(microsecond=0).isoformat())
    finished_at: str | None = None
    outcome: str | None = None
    step: int | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"active": self.active, "started_at": self.started_at, "finished_at": self.finished_at,
                "outcome": self.outcome, "step": self.step, "reason": self.reason}


class RunnerRegistry:
    def __init__(self, base_dir: str | Path, agents_factory: AgentsFactory,
                 poll_seconds: float = POLL_SECONDS, timeout_seconds: float = WAIT_TIMEOUT_SECONDS) -> None:
        self.base_dir = Path(base_dir)
        self.agents_factory = agents_factory
        self.poll_seconds = poll_seconds
        self.timeout_seconds = timeout_seconds
        self._lock = threading.Lock()
        self._states: dict[str, RunnerState] = {}
        self._threads: dict[str, threading.Thread] = {}

    def status(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            state = self._states.get(run_id)
            return state.to_dict() if state else None

    def start(self, run_id: str, retry_rejected: bool = False) -> RunnerState:
        with self._lock:
            current = self._states.get(run_id)
            if current is not None and current.active:
                raise RunnerBusy(f"la ejecución {run_id!r} ya está en curso")
            state = RunnerState(run_id)
            self._states[run_id] = state
            thread = threading.Thread(target=self._work, args=(state, retry_rejected),
                                      name=f"orquestador-{run_id}", daemon=True)
            self._threads[run_id] = thread
        thread.start()
        return state

    def join(self, run_id: str, timeout: float | None = None) -> None:
        thread = self._threads.get(run_id)
        if thread is not None:
            thread.join(timeout)

    def _work(self, state: RunnerState, retry_rejected: bool) -> None:
        store = RunStore(state.run_id, self.base_dir)
        try:
            result = orch.run(store, self.agents_factory(), wait=True, poll_seconds=self.poll_seconds,
                              timeout_seconds=self.timeout_seconds, retry_rejected=retry_rejected,
                              log=lambda m: print(f"[{state.run_id}] {m}", flush=True))
            outcome, step, reason = result.outcome, result.step, result.reason
        except Exception as exc:  # noqa: BLE001 - el hilo nunca debe morir sin dejar rastro
            traceback.print_exc()
            outcome, step, reason = orch.FAILED, None, f"{type(exc).__name__}: {exc}"
            store.audit(orch.ACTOR, "flow_stopped", outcome=outcome, reason=reason)
        with self._lock:
            state.active = False
            state.finished_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            state.outcome, state.step, state.reason = outcome, step, reason
