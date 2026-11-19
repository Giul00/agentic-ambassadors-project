"""Agente SysOps: transforma un cambio aprobado en un plan de despliegue auditable."""

from __future__ import annotations

import argparse
import sys

from delivery_crew.contracts import Change, Deployment, Design
from delivery_crew.runs import NotApprovedError, RunStore


DEFAULT_RESOURCES = [
    "AWS Lambda: actualización del handler auth-service",
    "Amazon DynamoDB: tabla de frecuencia con TTL de 60 segundos",
    "IAM: permiso mínimo de lectura/escritura de la Lambda sobre la tabla",
    "Amazon API Gateway: endpoint POST /authorize",
    "Amazon CloudWatch: logs, métricas y health check",
]
DEFAULT_ROLLBACK = (
    "Restaurar la versión previa aprobada de la Lambda, verificar el endpoint y revisar CloudWatch. "
    "No eliminar la tabla DynamoDB automáticamente para preservar evidencia de auditoría."
)


def select_template_profiles(design: Design) -> list[str]:
    """Select only catalog profiles justified by Architecture's approved components."""
    components = " ".join(design.components).lower()
    profiles: list[str] = []
    if "dynamodb" in components or "lambda" in components or "auth-service" in components:
        profiles.append("lambda_dynamodb")
    if "s3" in components:
        profiles.append("s3")
    if "cloudwatch" in components or "alarma" in components:
        profiles.append("cloudwatch_alarm")
    if "ecs" in components or "fargate" in components:
        profiles.append("ecs_fargate")
    return profiles


def create_plan(run_id: str, target_account_id: str, region: str = "us-west-2", base_dir: str = "runs") -> Deployment:
    """Create step 04 only when the developer's step 03 is human-approved."""
    store = RunStore(run_id, base_dir=base_dir)
    design = store.read(Design)
    if design.approval.status != "aprobado":
        raise NotApprovedError("02-diseno.md no está aprobado; SysOps no puede elegir infraestructura")
    change = store.read_input_for(4, Change)
    profiles = select_template_profiles(design)
    if not profiles:
        raise ValueError("el diseño aprobado no declara componentes con perfil de infraestructura conocido")
    resources = list(DEFAULT_RESOURCES)
    if not any(path.startswith("infra/") for path in change.files_modified):
        resources.append("Nota: el PR no contiene IaC; SysOps aplica la infraestructura versionada en infra/.")
    deployment = Deployment(
        run_id=run_id,
        target_account_id=target_account_id,
        region=region,
        resources=resources,
        estimated_cost_usd=0.05,
        rollback_plan=DEFAULT_ROLLBACK,
        health_check="pendiente",
        body=(f"Plan generado para la rama `{change.branch}`. Pruebas del desarrollador: {change.test_summary}.\n\n"
              f"Diseño de Arquitectura: {design.decision}\n"
              f"Perfiles seleccionados desde `templates/sysops/catalog.yml`: {', '.join(profiles)}.\n\n"
              "Pendiente de aprobación humana de SysOps. Este agente no ejecuta `cdk deploy`."),
    )
    store.write(deployment, actor="agente-despliegue")
    store.audit("agente-despliegue", "deployment_plan_created", source_branch=change.branch)
    return deployment


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genera 04-despliegue.md desde un 03-cambio.md aprobado.")
    parser.add_argument("run_id")
    parser.add_argument("--target-account", required=True)
    parser.add_argument("--region", default="us-west-2")
    parser.add_argument("--runs-dir", default="runs")
    args = parser.parse_args(argv)
    try:
        plan = create_plan(args.run_id, args.target_account, args.region, args.runs_dir)
    except (FileNotFoundError, NotApprovedError, ValueError) as exc:
        print(f"No se pudo generar el plan: {exc}", file=sys.stderr)
        return 2
    print(f"Plan generado: {RunStore(args.run_id, args.runs_dir).path / plan.FILENAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
