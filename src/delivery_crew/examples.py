"""Artefactos de ejemplo del caso demo (código de rechazo 65). Sirven de referencia y para pruebas.

Para regenerar los archivos de docs/ejemplos/:  python -m delivery_crew.examples docs/ejemplos
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

from .contracts import (
    Approval,
    Change,
    DeployableArtifact,
    Deployment,
    DeploymentComponent,
    DeploymentSpec,
    Design,
    Requirement,
)
from .conventions import LAMBDA_BUILD_COMMAND, LAMBDA_ENTRYPOINT
from .runs import RunStore

DEMO_RUN_ID = "demo-0001"
_T = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _approved(by: str) -> Approval:
    return Approval(status="aprobado", by=by, at=_T)


def requirement(run_id: str = DEMO_RUN_ID, approved: bool = True) -> Requirement:
    return Requirement(
        run_id=run_id,
        created_at=_T,
        title="Código de rechazo 65 por límite de frecuencia",
        description=(
            "Si un mismo card_token hace más de 3 solicitudes en 60 segundos, "
            "auth-service debe rechazar con response_code 65 y un mensaje claro."
        ),
        acceptance_criteria=[
            "La cuarta solicitud en 60 segundos devuelve response_code 65.",
            "Las tres primeras solicitudes no se ven afectadas.",
            "El código 65 aparece en la respuesta de la API.",
        ],
        affected_service="auth-service",
        approval=_approved("usuario") if approved else Approval(),
    )


def design(run_id: str = DEMO_RUN_ID, approved: bool = True) -> Design:
    return Design(
        run_id=run_id,
        created_at=_T,
        summary="Contar solicitudes por card_token en una tabla DynamoDB con TTL de 60 segundos.",
        components=["auth-service (reglas)", "DynamoDB: tabla de frecuencia"],
        decision="Usar DynamoDB con contador atómico y TTL en lugar de memoria de la Lambda.",
        risks=["Costo por escritura en cada solicitud.", "Latencia extra de una llamada a DynamoDB."],
        verdict="aprobado",
        standards_cited=["Permisos mínimos", "Sin datos de tarjeta reales"],
        deployment_spec=DeploymentSpec(
            environment="qa",
            components=[
                DeploymentComponent(name="auth-api", kind="api_gateway", depends_on=["auth-handler"]),
                DeploymentComponent(name="auth-handler", kind="lambda", depends_on=["frequency-store"],
                                    configuration={"FREQUENCY_STORE": "dynamodb"}),
                DeploymentComponent(name="frequency-store", kind="dynamodb",
                                    configuration={"partition_key": "pk", "ttl_attribute": "ttl"}),
            ],
            network_exposure="public",
            data_classification="synthetic",
            health_check="POST /authorize: tres 00 y luego 65",
            rollback_strategy="Restaurar la versión Lambda aprobada previamente y verificar el endpoint.",
            observability=["CloudWatch logs", "métrica de errores Lambda"],
        ),
        body="Diagrama y detalle del diseño.",
        approval=_approved("arquitecto") if approved else Approval(),
    )


def change(run_id: str = DEMO_RUN_ID, approved: bool = True) -> Change:
    return Change(
        run_id=run_id,
        created_at=_T,
        branch="feature/codigo-65-frecuencia",
        pull_request_url="https://github.com/Giul00/agentic-ambassadors-project/pull/1",
        files_modified=["services/auth_service/auth_service/rules.py", "services/auth_service/tests/test_auth_rules.py"],
        test_result="passed",
        test_summary="12 pruebas, 12 correctas.",
        deliverables=[DeployableArtifact(component="auth-handler", kind="zip", source_path="services/auth_service",
                                         build_command=LAMBDA_BUILD_COMMAND, entrypoint=LAMBDA_ENTRYPOINT)],
        approval=_approved("desarrollador") if approved else Approval(),
    )


def deployment(run_id: str = DEMO_RUN_ID, approved: bool = True) -> Deployment:
    return Deployment(
        run_id=run_id,
        created_at=_T,
        target_account_id="123456789012",  # ID de ejemplo, no es una cuenta real
        region="us-west-2",
        resources=["DynamoDB: tabla de frecuencia", "IAM: permiso de lectura y escritura para la Lambda"],
        estimated_cost_usd=0.05,
        rollback_plan="Volver a la versión anterior de la Lambda y eliminar la tabla creada.",
        health_check="ok",
        approval=_approved("sysops") if approved else Approval(),
    )


def write_demo_run(base_dir: str | Path, run_id: str = DEMO_RUN_ID) -> RunStore:
    store = RunStore(run_id, base_dir).create()
    for artifact in (requirement(run_id), design(run_id), change(run_id), deployment(run_id)):
        store.write(artifact, actor="ejemplo")
    return store


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/ejemplos")
    store = write_demo_run(target)
    store.audit_path.unlink(missing_ok=True)  # la auditoría de ejemplo no aporta
    print(f"Ejemplos escritos en {store.path}")
