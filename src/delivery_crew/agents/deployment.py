"""Agente SysOps: transforma un cambio aprobado en un plan de despliegue auditable."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import shutil
import sys

import yaml

from delivery_crew.contracts import Change, Deployment, Design
from delivery_crew.conventions import SAFE_VALUE
from delivery_crew.runs import NotApprovedError, RunStore


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
TEMPLATE_ROOT = REPOSITORY_ROOT / "templates" / "sysops"

# Traducción de la configuración de Arquitectura a parámetros de la plantilla lambda-dynamodb.
TEMPLATE_PARAMETERS: dict[str, dict[str, str]] = {
    "dynamodb": {"partition_key": "TablePartitionKey", "ttl_attribute": "TableTtlAttribute"},
    "lambda": {"STORAGE_BACKEND": "StorageBackend"},
}
PIPELINE_EXTRA_OVERRIDES = 'CF_EXTRA_PARAMETER_OVERRIDES: ""'


def package_of(artifact) -> str:
    """Paquete Python del entregable, tomado del entrypoint (<paquete>.handler.lambda_handler)."""
    entry = artifact.entrypoint or ""
    package = entry.split(".")[0] if entry else Path(artifact.source_path).name
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,40}", package or ""):
        raise ValueError(f"no se puede determinar el paquete del entregable de {artifact.component}")
    return package


def parameter_overrides(design: Design, change: Change, source_root: Path | None = None) -> dict[str, str]:
    """Parámetros de CloudFormation a partir del deployment_spec y los entregables.

    Falla si la configuración no tiene parámetro en la plantilla, si dos componentes piden
    valores distintos para el mismo parámetro, o si un entregable apunta a una ruta inexistente.
    """
    spec = design.deployment_spec
    if spec is None:
        raise ValueError("el diseño no contiene deployment_spec estructurado")
    overrides: dict[str, str] = {}

    def put(parameter: str, value: str, origin: str) -> None:
        if not SAFE_VALUE.fullmatch(value):
            raise ValueError(f"valor no permitido para {parameter} ({origin}): {value!r}")
        if overrides.get(parameter, value) != value:
            raise ValueError(f"valores en conflicto para {parameter}: {overrides[parameter]!r} y {value!r}")
        overrides[parameter] = value

    for component in spec.components:
        mapping = TEMPLATE_PARAMETERS.get(component.kind, {})
        unsupported = sorted(set(component.configuration) - set(mapping))
        if unsupported:
            raise ValueError(
                f"la plantilla no soporta la configuración de {component.name}: {', '.join(unsupported)}"
            )
        for key, value in component.configuration.items():
            put(mapping[key], value, component.name)

    lambdas = {c.name for c in spec.components if c.kind == "lambda"}
    for artifact in change.deliverables:
        root = (source_root or REPOSITORY_ROOT).resolve()
        source = (root / artifact.source_path).resolve()
        if (source != root and root not in source.parents) or not source.is_dir():
            raise ValueError(f"el entregable de {artifact.component} apunta a una ruta inexistente: {artifact.source_path}")
        if artifact.component in lambdas and artifact.entrypoint:
            put("LambdaHandler", artifact.entrypoint, artifact.component)
    return overrides


def select_template_profiles(design: Design) -> list[str]:
    """Compose catalog profiles from Architecture's structured deployment spec."""
    if not design.deployment_spec:
        raise ValueError("el diseño no contiene deployment_spec estructurado")
    catalog = yaml.safe_load((TEMPLATE_ROOT / "catalog.yml").read_text(encoding="utf-8"))
    required = {component.kind for component in design.deployment_spec.components}
    selected: list[str] = []
    covered: set[str] = set()
    for name, profile in catalog["profiles"].items():
        capabilities = set(profile.get("capabilities", []))
        if capabilities and capabilities.issubset(required):
            if profile.get("status", "ready") != "ready":
                raise ValueError(f"el perfil {name!r} aún no está homologado para despliegue")
            selected.append(name)
            covered.update(capabilities)
    missing = required - covered
    if missing:
        raise ValueError(f"no hay perfil homologado para los componentes: {', '.join(sorted(missing))}")
    return selected


def generate_bundle(store: RunStore, design: Design, change: Change, deployment: Deployment, profiles: list[str],
                    overrides: dict[str, str] | None = None) -> Path:
    """Render reviewable IaC, pipeline and verification assets for a run.

    The output is intentionally an artifact of the run: it is reviewed and promoted
    into the delivery branch only after SysOps approves the associated Deployment.
    """
    catalog = yaml.safe_load((TEMPLATE_ROOT / "catalog.yml").read_text(encoding="utf-8"))
    bundle = store.path / "generated"
    cloudformation = bundle / "cloudformation"
    scripts = bundle / "scripts"
    cloudformation.mkdir(parents=True, exist_ok=True)
    scripts.mkdir(parents=True, exist_ok=True)

    selected_templates: list[str] = []
    for profile in profiles:
        details = catalog["profiles"][profile]
        source_relative = details.get("template")
        if not source_relative:
            raise ValueError(f"el perfil {profile!r} todavía no tiene una plantilla normalizada")
        source = TEMPLATE_ROOT / source_relative
        target = cloudformation / source.name
        shutil.copyfile(source, target)
        selected_templates.append(str(Path("cloudformation") / source.name))

    primary_template = selected_templates[0]
    pipeline = (TEMPLATE_ROOT / catalog["pipeline"]["template"]).read_text(encoding="utf-8")
    pipeline = pipeline.replace("templates/generated/stack.yml", f"generated/{primary_template}")
    pipeline = pipeline.replace("./scripts/health-check.sh", "./generated/scripts/health-check-authorize.sh")
    overrides = overrides or {}
    if overrides:
        if PIPELINE_EXTRA_OVERRIDES not in pipeline:
            raise ValueError("la plantilla del pipeline no admite parámetros adicionales")
        rendered = " ".join(f"{key}={value}" for key, value in sorted(overrides.items()))
        pipeline = pipeline.replace(PIPELINE_EXTRA_OVERRIDES, f'CF_EXTRA_PARAMETER_OVERRIDES: "{rendered}"')
    zips = [a for a in change.deliverables if a.kind == "zip"]
    if zips:
        source = zips[0].source_path
        package = package_of(zips[0])
        if not SAFE_VALUE.fullmatch(package) or not re.fullmatch(r"[A-Za-z0-9_/.-]{1,120}", source) or ".." in source:
            raise ValueError(f"ruta de entregable no permitida en el pipeline: {source!r}")
        pipeline = pipeline.replace("  SERVICE_DIR: services/auth_service", f"  SERVICE_DIR: {source}")
        pipeline = pipeline.replace("  SERVICE_PACKAGE: auth_service", f"  SERVICE_PACKAGE: {package}")
    (bundle / ".gitlab-ci-sysops.yml").write_text(pipeline, encoding="utf-8")
    shutil.copyfile(TEMPLATE_ROOT / "health-check-authorize.sh", scripts / "health-check-authorize.sh")

    manifest = {
        "run_id": deployment.run_id,
        "source_branch": change.branch,
        "architecture_decision": design.decision,
        "deployment_spec": design.deployment_spec.model_dump(mode="json") if design.deployment_spec else None,
        "deliverables": [artifact.model_dump(mode="json") for artifact in change.deliverables],
        "target_account_id": deployment.target_account_id,
        "region": deployment.region,
        "template_profiles": profiles,
        "cloudformation_templates": selected_templates,
        "parameter_overrides": overrides,
        "pipeline": ".gitlab-ci-sysops.yml",
        "health_check": "scripts/health-check-authorize.sh",
        "required_ci_variables": ["AWS_DEFAULT_REGION", "CF_STACK_NAME", "HEALTHCHECK_URL", "PREVIOUS_APPROVED_TEMPLATE"],
        "status": "pending_sysops_approval",
    }
    (bundle / "manifest.yml").write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8")
    store.audit("agente-despliegue", "deployment_bundle_generated", profiles=profiles, bundle=str(bundle))
    return bundle


def stack_identity(design: Design, change: Change) -> tuple[str, str, str]:
    """(project_name, environment, stack_name) a partir del servicio entregado y el ambiente del diseño."""
    assert design.deployment_spec is not None
    environment = design.deployment_spec.environment
    lambdas = [a for a in change.deliverables if a.kind == "zip"]
    service = package_of(lambdas[0]).replace("_", "-") if lambdas else "app"
    project = f"dc-{service}"[:30].rstrip("-")
    return project, environment, f"{project}-{environment}"


def create_plan(run_id: str, target_account_id: str, region: str = "us-west-2", base_dir: str = "runs") -> Deployment:
    """Create step 04 only when the developer's step 03 is human-approved."""
    store = RunStore(run_id, base_dir=base_dir)
    design = store.read(Design)
    if design.approval.status != "aprobado":
        raise NotApprovedError("02-diseno.md no está aprobado; SysOps no puede elegir infraestructura")
    change = store.read_input_for(4, Change)
    profiles = select_template_profiles(design)
    spec = design.deployment_spec
    assert spec is not None  # validated by select_template_profiles
    compute_components = {component.name for component in spec.components if component.kind in {"lambda", "ecs", "container"}}
    artifact_components = {artifact.component for artifact in change.deliverables}
    missing_artifacts = compute_components - artifact_components
    if missing_artifacts:
        raise ValueError(f"Desarrollo no entregó artefactos para: {', '.join(sorted(missing_artifacts))}")
    from delivery_crew.workspace import WorkspaceError, code_root

    try:
        root = code_root(store, REPOSITORY_ROOT)
    except WorkspaceError as exc:
        raise ValueError(str(exc)) from exc
    overrides = parameter_overrides(design, change, root)
    project, environment, stack_name = stack_identity(design, change)
    resources = [f"{component.kind}: {component.name}" for component in spec.components]
    resources.extend(f"Observabilidad: {item}" for item in spec.observability)
    deployment = Deployment(
        run_id=run_id,
        target_account_id=target_account_id,
        region=region,
        resources=resources,
        estimated_cost_usd=0.05 * len(profiles),
        rollback_plan=spec.rollback_strategy,
        health_check="pendiente",
        stack_name=stack_name,
        project_name=project,
        environment=environment,
        body=(f"Plan generado para la rama `{change.branch}`. Pruebas del desarrollador: {change.test_summary}.\n\n"
              f"Diseño de Arquitectura: {design.decision}\n"
              f"Health check aprobado: {spec.health_check}\n"
              f"Perfiles seleccionados desde `templates/sysops/catalog.yml`: {', '.join(profiles)}.\n"
              f"Parámetros de la plantilla: {', '.join(f'{k}={v}' for k, v in sorted(overrides.items())) or 'por defecto'}.\n"
              f"Stack de CloudFormation: `{stack_name}` en {region}, cuenta {target_account_id}.\n\n"
              "Al aprobar este plan, el ejecutor crea un change set con estos valores, lo ejecuta y corre la prueba "
              "de humo del servicio contra la URL desplegada."),
    )
    store.write(deployment, actor="agente-despliegue")
    bundle = generate_bundle(store, design, change, deployment, profiles, overrides)
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
