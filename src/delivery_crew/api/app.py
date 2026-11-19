"""API HTTP del panel. Ejecutar con:  python -m delivery_crew.api

Pensada para correr en la laptop de quien presenta (127.0.0.1). No tiene autenticación,
por eso no debe exponerse a una red abierta.

Variables de entorno:
  DELIVERY_CREW_RUNS_DIR   carpeta de ejecuciones (por defecto: runs)
  DELIVERY_CREW_CORS       orígenes permitidos separados por coma
                           (por defecto: http://localhost:5173,http://localhost:3000)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ValidationError, model_validator

from .. import orchestrator as orch
from ..bedrock import model_id, region as default_region
from ..contracts import Requirement
from ..runs import RunStore
from . import service
from .runner import AgentsFactory, RunnerBusy, RunnerRegistry


class NewRunIn(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=10, max_length=2000)
    acceptance_criteria: list[str] = Field(min_length=1, max_length=10)
    affected_service: str = Field(default="auth-service", pattern=r"^[a-z][a-z0-9-]{1,40}$")
    requested_by: str = Field(min_length=1, max_length=80)

    @model_validator(mode="after")
    def _clean_criteria(self) -> "NewRunIn":
        self.acceptance_criteria = [c.strip() for c in self.acceptance_criteria if c and c.strip()]
        if not self.acceptance_criteria:
            raise ValueError("se necesita al menos un criterio de aceptación")
        if any(len(c) > 300 for c in self.acceptance_criteria):
            raise ValueError("cada criterio de aceptación admite hasta 300 caracteres")
        return self


class ResumeIn(BaseModel):
    retry_rejected: bool = False


class DecisionIn(BaseModel):
    status: Literal["aprobado", "rechazado"]
    by: str = Field(min_length=1, max_length=80, description="Nombre de quien decide")
    reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _reject_needs_reason(self) -> "DecisionIn":
        if self.status == "rechazado" and not (self.reason and self.reason.strip()):
            raise ValueError("un rechazo debe indicar el motivo ('reason')")
        return self


def create_app(runs_dir: str | Path | None = None, agents_factory: AgentsFactory | None = None,
               target_account: str | None = None, repo: str | Path | None = None,
               region: str | None = None) -> FastAPI:
    base = Path(runs_dir or os.environ.get("DELIVERY_CREW_RUNS_DIR", "runs"))
    target_account = target_account or os.environ.get("DELIVERY_CREW_TARGET_ACCOUNT") or None
    repo_path = Path(repo or os.environ.get("DELIVERY_CREW_REPO", ".")).resolve()
    aws_region = region or default_region()
    if agents_factory is None:
        def agents_factory() -> orch.Agents:
            return orch.default_agents(repo_path, target_account, aws_region)
    runners = RunnerRegistry(base, agents_factory)
    origins = [
        o.strip()
        for o in os.environ.get(
            "DELIVERY_CREW_CORS", "http://localhost:5173,http://localhost:3000"
        ).split(",")
        if o.strip()
    ]

    app = FastAPI(title="Delivery Crew: panel", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    def store_for(run_id: str) -> RunStore:
        try:
            store = RunStore(run_id, base)
        except ValueError:
            raise HTTPException(status_code=400, detail="identificador de ejecución inválido")
        if not store.path.is_dir():
            raise HTTPException(status_code=404, detail=f"no existe la ejecución {run_id!r}")
        return store

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "runs_dir": str(base)}

    @app.get("/api/config")
    def config() -> dict:
        return {"target_account": target_account, "region": aws_region, "model_id": model_id()}

    @app.get("/api/runs")
    def list_runs() -> list[dict]:
        return [service.summary(RunStore(rid, base)) for rid in service.list_run_ids(base)]

    @app.post("/api/runs", status_code=201)
    def create_run(body: NewRunIn) -> dict:
        run_id = orch.make_run_id(body.title)
        store = RunStore(run_id, base)
        try:
            requirement = Requirement(run_id=run_id, title=body.title.strip(), description=body.description.strip(),
                                      acceptance_criteria=body.acceptance_criteria,
                                      affected_service=body.affected_service)
            orch.start(store, requirement, requested_by=body.requested_by.strip())
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=[e["msg"] for e in exc.errors()])
        except FileExistsError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        runners.start(run_id)
        return {**service.detail(store), "runner": runners.status(run_id)}

    @app.post("/api/runs/{run_id}/resume")
    def resume_run(run_id: str, body: ResumeIn) -> dict:
        store = store_for(run_id)
        if service.overall_state(service.load_stages(store)) == "completo":
            raise HTTPException(status_code=409, detail="la ejecución ya está completa")
        try:
            runners.start(run_id, retry_rejected=body.retry_rejected)
        except RunnerBusy as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        return {**service.detail(store), "runner": runners.status(run_id)}

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict:
        return {**service.detail(store_for(run_id)), "runner": runners.status(run_id)}

    @app.get("/api/runs/{run_id}/audit")
    def get_audit(run_id: str) -> list[dict]:
        return store_for(run_id).read_audit()

    @app.post("/api/runs/{run_id}/stages/{step}/decision")
    def post_decision(run_id: str, step: int, body: DecisionIn) -> dict:
        store = store_for(run_id)
        try:
            return {**service.decide(store, step, body.status, body.by.strip(), body.reason),
                    "runner": runners.status(run_id)}
        except service.DecisionError as exc:
            raise HTTPException(status_code=409, detail=str(exc))

    app.state.runners = runners
    return app


app = create_app()
