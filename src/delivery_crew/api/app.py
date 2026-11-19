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
from pydantic import BaseModel, Field, model_validator

from ..runs import RunStore
from . import service


class DecisionIn(BaseModel):
    status: Literal["aprobado", "rechazado"]
    by: str = Field(min_length=1, max_length=80, description="Nombre de quien decide")
    reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _reject_needs_reason(self) -> "DecisionIn":
        if self.status == "rechazado" and not (self.reason and self.reason.strip()):
            raise ValueError("un rechazo debe indicar el motivo ('reason')")
        return self


def create_app(runs_dir: str | Path | None = None) -> FastAPI:
    base = Path(runs_dir or os.environ.get("DELIVERY_CREW_RUNS_DIR", "runs"))
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

    @app.get("/api/runs")
    def list_runs() -> list[dict]:
        return [service.summary(RunStore(rid, base)) for rid in service.list_run_ids(base)]

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict:
        return service.detail(store_for(run_id))

    @app.get("/api/runs/{run_id}/audit")
    def get_audit(run_id: str) -> list[dict]:
        return store_for(run_id).read_audit()

    @app.post("/api/runs/{run_id}/stages/{step}/decision")
    def post_decision(run_id: str, step: int, body: DecisionIn) -> dict:
        store = store_for(run_id)
        try:
            return service.decide(store, step, body.status, body.by.strip(), body.reason)
        except service.DecisionError as exc:
            raise HTTPException(status_code=409, detail=str(exc))

    return app


app = create_app()
