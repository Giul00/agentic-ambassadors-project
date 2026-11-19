"""Agente SysOps: transforma un cambio aprobado en un plan de despliegue auditable."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys

import yaml

from delivery_crew.contracts import Change, Deployment, Design
from delivery_crew.runs import NotApprovedError, RunStore


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
TEMPLATE_ROOT = REPOSITORY_ROOT / "templates" / "sysops"


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


def generate_bundle(store: RunStore, design: Design, change: Change, deployment: Deployment, profiles: list[str]) -> Path:
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
        "pipeline": ".gitlab-ci-sysops.yml",
        "health_check": "scripts/health-check-authorize.sh",
        "required_ci_variables": ["AWS_DEFAULT_REGION", "CF_STACK_NAME", "HEALTHCHECK_URL", "PREVIOUS_APPROVED_TEMPLATE"],
        "status": "pending_sysops_approval",
    }
    (bundle / "manifest.yml").write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8")
    store.audit("agente-despliegue", "deployment_bundle_generated", profiles=profiles, bundle=str(bundle))
    return bundle


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
        body=(f"Plan generado para la rama `{change.branch}`. Pruebas del desarrollador: {change.test_summary}.\n\n"
              f"Diseño de Arquitectura: {design.decision}\n"
              f"Health check aprobado: {spec.health_check}\n"
              f"Perfiles seleccionados desde `templates/sysops/catalog.yml`: {', '.join(profiles)}.\n\n"
              "Pendiente de aprobación humana de SysOps. Este agente no ejecuta `cdk deploy`."),
    )
    store.write(deployment, actor="agente-despliegue")
    bundle = generate_bundle(store, design, change, deployment, profiles)
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
