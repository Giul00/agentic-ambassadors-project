"""Orquestador de Delivery Crew (unidad 06).

Coordina Arquitecto -> Desarrollador -> Despliegue sobre una ejecución en runs/<id>/.
Es una máquina de estados reanudable: en cada paso mira qué artefactos existen y en qué
estado están, y hace lo único que corresponde (correr un agente, esperar una decisión
humana o detenerse). Si se interrumpe, `resume` continúa donde quedó.

Las decisiones humanas pueden llegar:
  - desde el panel (API): el orquestador espera y relee runs/<id>/ periódicamente, o
  - desde la terminal, con --interactive.

Uso:
  python -m delivery_crew.orchestrator start --run-id demo-1 --example --by tomas --target-account 123456789012
  python -m delivery_crew.orchestrator resume --run-id demo-1 --target-account 123456789012 [--retry-rejected]
  python -m delivery_crew.orchestrator status --run-id demo-1
"""

from __future__ import annotations

import argparse
import re
import sys
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .api.service import LABELS, load_stages, overall_state
from .contracts import ARTIFACTS, Change, Design, Requirement
from .runs import RunStore

ACTOR = "orquestador"

# Resultados de un paso / de una corrida.
PROGRESSED = "progressed"            # se corrió un agente; hay que seguir
WAITING = "waiting_approval"         # hay un artefacto esperando decisión humana
COMPLETED = "completed"              # las cuatro etapas están aprobadas
REJECTED = "rejected"                # una persona rechazó una etapa
BLOCKED = "blocked"                  # aprobado, pero no se puede continuar (ver motivo)
INVALID = "invalid"                  # un artefacto no cumple el contrato
FAILED = "failed"                    # un agente falló

Log = Callable[[str], None]
Decider = Callable[[RunStore, int], None]


@dataclass
class Agents:
    """Cómo correr cada agente. En pruebas se reemplazan por funciones falsas."""

    architect: Callable[[RunStore], None]
    developer: Callable[[RunStore], None]
    deployment: Callable[[RunStore], None]

    def for_step(self, step: int) -> Callable[[RunStore], None]:
        return {2: self.architect, 3: self.developer, 4: self.deployment}[step]


@dataclass
class StepResult:
    outcome: str
    step: int | None = None
    reason: str | None = None


def default_agents(repo: str | Path = ".", target_account: str | None = None, region: str = "us-west-2",
                   log: Log = print) -> Agents:
    """Agentes reales (Bedrock). Se importan al usarlos para no exigir credenciales en pruebas."""

    def architect(store: RunStore) -> None:
        from .agents.architect import generate_design

        generate_design(store.run_id, store.path.parent)

    def developer(store: RunStore) -> None:
        from .agents.developer import run_developer

        # fresh=True: el paso solo se corre si no hay cambio o si fue rechazado; en ese caso,
        # el agente descarta su copia anterior y recibe el motivo del rechazo.
        run_developer(store, repo, fresh=True, log=lambda m: log(f"    {m}"))

    def deployment(store: RunStore) -> None:
        from .agents.deployment import create_plan

        if not target_account:
            raise ValueError("falta --target-account (cuenta de despliegue de 12 dígitos)")
        create_plan(store.run_id, target_account, region=region, base_dir=str(store.path.parent))

    return Agents(architect, developer, deployment)


# --- un paso -----------------------------------------------------------------

def _blocked_reason(store: RunStore, step: int) -> str | None:
    """Aprobaciones humanas que no alcanzan para continuar."""
    if step == 2:
        design = store.read(Design)
        if design.verdict != "aprobado":
            return (f"el diseño fue aprobado por una persona, pero su veredicto es '{design.verdict}'; "
                    "corrija el requerimiento o el diseño antes de implementar")
    if step == 3:
        change = store.read(Change)
        if change.test_result != "passed":
            return "el cambio fue aprobado con pruebas fallidas; no se puede planificar el despliegue"
    return None


def step_once(store: RunStore, agents: Agents, retry_rejected: bool = False, log: Log = print) -> StepResult:
    """Avanza una sola vez. Es idempotente: si nada cambió, devuelve el mismo resultado sin efectos."""
    for stage in load_stages(store):
        step = stage.step
        if stage.state == "aprobado":
            reason = _blocked_reason(store, step)
            if reason:
                return StepResult(BLOCKED, step, reason)
            continue
        if stage.state == "invalido":
            return StepResult(INVALID, step, stage.error)
        if stage.state == "rechazado":
            if retry_rejected and step == 3:
                log(f"Reintentando {LABELS[step]} con el motivo del rechazo...")
                return _run_agent(store, agents, step, log, retry=True)
            return StepResult(REJECTED, step, stage.artifact.approval.reason if stage.artifact else None)
        if stage.state == "por_aprobar":
            return StepResult(WAITING, step)
        if stage.state == "en_curso":
            if step == 1:
                return StepResult(INVALID, 1, "la ejecución no tiene requerimiento; use 'start'")
            return _run_agent(store, agents, step, log)
        return StepResult(INVALID, step, f"estado inesperado: {stage.state}")
    return StepResult(COMPLETED)


def _run_agent(store: RunStore, agents: Agents, step: int, log: Log, retry: bool = False) -> StepResult:
    label = LABELS[step]
    store.audit(ACTOR, "stage_started", step=step, stage=label, retry=retry or None)
    log(f"[{step}/4] {label}: trabajando...")
    started = time.monotonic()
    try:
        agents.for_step(step)(store)
    except Exception as exc:  # noqa: BLE001 - cualquier fallo de un agente detiene el flujo y se audita
        store.audit(ACTOR, "stage_failed", step=step, stage=label, error=f"{type(exc).__name__}: {exc}")
        return StepResult(FAILED, step, f"{type(exc).__name__}: {exc}")
    if not store.exists(ARTIFACTS[step - 1]):
        store.audit(ACTOR, "stage_failed", step=step, stage=label, error="el agente no escribió su artefacto")
        return StepResult(FAILED, step, "el agente no escribió su artefacto")
    seconds = round(time.monotonic() - started, 1)
    store.audit(ACTOR, "stage_finished", step=step, stage=label, seconds=seconds)
    log(f"[{step}/4] {label}: listo en {seconds} s")
    return StepResult(PROGRESSED, step)


# --- corrida completa -----------------------------------------------------------

def run(store: RunStore, agents: Agents, *, decide: Decider | None = None, wait: bool = True,
        poll_seconds: float = 2.0, timeout_seconds: float | None = None, retry_rejected: bool = False,
        log: Log = print, sleep: Callable[[float], None] = time.sleep) -> StepResult:
    """Avanza hasta terminar, detenerse o (si wait=False) quedar esperando una decisión."""
    deadline = None if timeout_seconds is None else time.monotonic() + timeout_seconds
    announced: int | None = None
    retry = retry_rejected
    while True:
        result = step_once(store, agents, retry_rejected=retry, log=log)
        retry = False  # el reintento se hace una sola vez por llamada
        if result.outcome == PROGRESSED:
            announced = None
            continue
        if result.outcome == WAITING:
            if decide is not None:
                decide(store, result.step)  # type: ignore[arg-type]
                continue
            if announced != result.step:
                store.audit(ACTOR, "waiting_approval", step=result.step, stage=LABELS[result.step])
                log(f"[{result.step}/4] {LABELS[result.step]}: esperando aprobación humana (panel o --interactive)")
                announced = result.step
            if not wait or (deadline is not None and time.monotonic() >= deadline):
                return result
            sleep(poll_seconds)
            continue
        _audit_end(store, result)
        return result


def _audit_end(store: RunStore, result: StepResult) -> None:
    if result.outcome == COMPLETED:
        store.audit(ACTOR, "flow_completed")
    else:
        store.audit(ACTOR, "flow_stopped", outcome=result.outcome, step=result.step, reason=result.reason)


# --- inicio --------------------------------------------------------------------

def start(store: RunStore, requirement: Requirement, requested_by: str) -> None:
    """Crea la ejecución con el requerimiento. Quien lo pide lo aprueba al crearlo."""
    if store.exists(Requirement):
        raise FileExistsError(f"la ejecución {store.run_id!r} ya existe; use 'resume'")
    store.create()
    store.write(requirement, actor=ACTOR)
    store.decide(Requirement, "aprobado", by=requested_by)


def make_run_id(title: str) -> str:
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_title.lower()).strip("-")[:40].strip("-") or "run"
    return f"{slug}-{time.strftime('%Y%m%d-%H%M%S')}"


# --- decisión por terminal --------------------------------------------------------

def summarize(store: RunStore, step: int) -> str:
    artifact = store.read(ARTIFACTS[step - 1])
    if isinstance(artifact, Design):
        lines = [f"Veredicto: {artifact.verdict}", f"Resumen: {artifact.summary}", f"Decisión: {artifact.decision}"]
        if artifact.standards_cited:
            lines.append(f"Estándares: {', '.join(artifact.standards_cited)}")
        if artifact.open_questions:
            lines += ["Preguntas abiertas:"] + [f"  - {q}" for q in artifact.open_questions]
        if artifact.deployment_spec:
            lines.append("Componentes: " + ", ".join(f"{c.name} ({c.kind})" for c in artifact.deployment_spec.components))
        return "\n".join(lines)
    if isinstance(artifact, Change):
        return "\n".join([f"Rama: {artifact.branch}", f"Pruebas: {artifact.test_result} ({artifact.test_summary})",
                          "Archivos:"] + [f"  - {f}" for f in artifact.files_modified])
    data = artifact.model_dump(exclude={"body", "approval", "run_id", "created_at"})
    return "\n".join(f"{k}: {v}" for k, v in data.items())


def terminal_decider(by: str, ask: Callable[[str], str] = input, out: Log = print) -> Decider:
    def decide(store: RunStore, step: int) -> None:
        out(f"\n--- {LABELS[step]} ({ARTIFACTS[step - 1].FILENAME}) ---")
        out(summarize(store, step))
        out(f"Detalle completo: {store.path / ARTIFACTS[step - 1].FILENAME}")
        while True:
            answer = ask("¿Aprobar? [a]probar / [r]echazar: ").strip().lower()
            if answer in ("a", "aprobar"):
                store.decide(ARTIFACTS[step - 1], "aprobado", by=by)
                return
            if answer in ("r", "rechazar"):
                reason = ""
                while not reason:
                    reason = ask("Motivo del rechazo: ").strip()
                store.decide(ARTIFACTS[step - 1], "rechazado", by=by, reason=reason)
                return
    return decide


# --- CLI -----------------------------------------------------------------------

def _print_status(store: RunStore) -> None:
    stages = load_stages(store)
    print(f"Ejecución {store.run_id}: {overall_state(stages)}")
    for s in stages:
        print(f"  {s.step}. {LABELS[s.step]:<14} {s.state}")


def _report(result: StepResult, store: RunStore) -> int:
    messages = {
        COMPLETED: "Flujo completo: las cuatro etapas están aprobadas.",
        WAITING: "Pausado: esperando una decisión humana. Continúe con 'resume'.",
        REJECTED: "Detenido: una etapa fue rechazada.",
        BLOCKED: "Detenido: no se puede continuar.",
        INVALID: "Detenido: un artefacto no cumple el contrato.",
        FAILED: "Detenido: un agente falló.",
    }
    print(f"\n{messages.get(result.outcome, result.outcome)}")
    if result.step:
        print(f"Etapa: {result.step}. {LABELS[result.step]}")
    if result.reason:
        print(f"Motivo: {result.reason}")
    if result.outcome == REJECTED and result.step == 3:
        print("Para que el agente lo corrija con ese motivo: resume --retry-rejected")
    _print_status(store)
    return 0 if result.outcome in (COMPLETED, WAITING) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Orquestador de Delivery Crew")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--runs-dir", default="runs")
        p.add_argument("--repo", default=".", help="raíz del repositorio (para el agente Desarrollador)")
        p.add_argument("--target-account", help="cuenta AWS de despliegue (12 dígitos)")
        p.add_argument("--region", default="us-west-2")
        p.add_argument("--interactive", action="store_true", help="decidir en la terminal en lugar del panel")
        p.add_argument("--by", default=None, help="nombre de quien decide (con --interactive) o pide (start)")
        p.add_argument("--no-wait", action="store_true", help="no esperar decisiones del panel; salir al quedar pendiente")
        p.add_argument("--poll", type=float, default=2.0, help="segundos entre lecturas mientras espera")

    p_start = sub.add_parser("start", help="crear una ejecución y correr el flujo")
    common(p_start)
    p_start.add_argument("--run-id")
    p_start.add_argument("--example", action="store_true", help="usar el requerimiento del caso demo (código 65)")
    p_start.add_argument("--title")
    p_start.add_argument("--description")
    p_start.add_argument("--criterion", action="append", default=[], help="criterio de aceptación (repetible)")
    p_start.add_argument("--service", default="auth-service")

    p_resume = sub.add_parser("resume", help="continuar una ejecución existente")
    common(p_resume)
    p_resume.add_argument("--run-id", required=True)
    p_resume.add_argument("--retry-rejected", action="store_true",
                          help="si el cambio de código fue rechazado, reintentar con el motivo")

    p_status = sub.add_parser("status", help="mostrar el estado de una ejecución")
    p_status.add_argument("--run-id", required=True)
    p_status.add_argument("--runs-dir", default="runs")

    args = parser.parse_args(argv)

    if args.command == "status":
        store = RunStore(args.run_id, args.runs_dir)
        if not store.path.is_dir():
            print(f"No existe la ejecución {args.run_id!r}")
            return 1
        _print_status(store)
        return 0

    if args.target_account and not re.fullmatch(r"\d{12}", args.target_account):
        print("--target-account debe tener 12 dígitos")
        return 2
    if args.interactive and not args.by:
        print("--interactive requiere --by <nombre>")
        return 2

    if args.command == "start":
        from . import examples

        if args.example:
            base = examples.requirement()
            fields = dict(title=base.title, description=base.description,
                          acceptance_criteria=base.acceptance_criteria, affected_service=base.affected_service)
        else:
            if not (args.title and args.description and args.criterion):
                print("start requiere --example, o --title, --description y al menos un --criterion")
                return 2
            fields = dict(title=args.title, description=args.description,
                          acceptance_criteria=args.criterion, affected_service=args.service)
        run_id = args.run_id or make_run_id(fields["title"])
        store = RunStore(run_id, args.runs_dir)
        try:
            start(store, Requirement(run_id=run_id, **fields), requested_by=args.by or "usuario")
        except FileExistsError as exc:
            print(exc)
            return 1
        print(f"Ejecución creada: {store.path}")
    else:
        store = RunStore(args.run_id, args.runs_dir)
        if not store.path.is_dir():
            print(f"No existe la ejecución {args.run_id!r}")
            return 1

    agents = default_agents(args.repo, args.target_account, args.region)
    decide = terminal_decider(args.by) if args.interactive else None
    try:
        result = run(store, agents, decide=decide, wait=not args.no_wait, poll_seconds=args.poll,
                     retry_rejected=getattr(args, "retry_rejected", False))
    except KeyboardInterrupt:
        print("\nInterrumpido. Continúe con 'resume'.")
        return 130
    return _report(result, store)


if __name__ == "__main__":
    sys.exit(main())
