"""Agente SysOps: transforma un cambio aprobado en un plan de despliegue auditable."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
from typing import Callable

import yaml

from delivery_crew.contracts import Change, Deployment, Design
from delivery_crew.runs import NotApprovedError, RunStore


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
TEMPLATE_ROOT = REPOSITORY_ROOT / "templates" / "sysops"
IacGenerator = Callable[[str], str]


class InfrastructureGenerationError(ValueError):
    """La propuesta de IaC no respeta el contrato o los controles operativos."""


class TemplateLibrary:
    """Contexto de patrones revisados que un generador puede consultar sin usar secretos."""

    def __init__(self, root: Path = TEMPLATE_ROOT) -> None:
        self.root = root
        self.catalog = yaml.safe_load((root / "catalog.yml").read_text(encoding="utf-8"))

    def search(self, component_kinds: set[str]) -> dict[str, dict]:
        """Devuelve patrones relevantes, incluso los no homologados, solo como referencia."""
        return {
            name: profile for name, profile in self.catalog["profiles"].items()
            if component_kinds.intersection(profile.get("capabilities", []))
        }

    def read_template(self, relative_path: str) -> str:
        """Lee una plantilla del catálogo y rechaza rutas fuera de la biblioteca."""
        path = (self.root / relative_path).resolve()
        if self.root.resolve() not in path.parents:
            raise InfrastructureGenerationError("ruta de plantilla fuera de la biblioteca")
        return path.read_text(encoding="utf-8")

    def context_for(self, design: Design) -> str:
        assert design.deployment_spec is not None
        kinds = {component.kind for component in design.deployment_spec.components}
        profiles = self.search(kinds)
        references: dict[str, str] = {}
        for name, profile in profiles.items():
            template = profile.get("template")
            if template:
                references[name] = self.read_template(template)
        return yaml.safe_dump(
            {"profiles": profiles, "reference_templates": references},
            sort_keys=False,
            allow_unicode=True,
        )


def build_iac_prompt(design: Design, change: Change, library: TemplateLibrary | None = None) -> str:
    """Construye el pedido para IaC libre, limitado por el contrato y patrones corporativos."""
    if not design.deployment_spec:
        raise InfrastructureGenerationError("el diseño no contiene deployment_spec estructurado")
    library = library or TemplateLibrary()
    spec = design.deployment_spec.model_dump(mode="json")
    artifacts = [artifact.model_dump(mode="json") for artifact in change.deliverables]
    return f"""Eres SysOps. Genera IaC y GitLab CI exclusivamente para el diseño aprobado.

Devuelve ÚNICAMENTE este formato, con YAML válido dentro de cada bloque:
<cloudformation>
AWSTemplateFormatVersion: '2010-09-09'
Resources: {{}}
</cloudformation>
<gitlab_ci>
stages: [test, versionador, build, deploy, deploy_QA, deploy_UAT, deploy_PROD]
</gitlab_ci>

Restricciones obligatorias:
- Implementa todos y solo los componentes del deployment_spec, respetando dependencias y configuración.
- Usa los deliverables para empaquetado, rutas y entrypoints. No inventes artefactos.
- No uses secretos, credenciales, IDs de cuenta, ARNs fijos, nombres internos ni valores productivos.
- Parametriza nombres, ambiente y ubicaciones; agrega tags project/environment.
- IAM de mínimo privilegio; cifrado y logs cuando correspondan.
- El CI debe validar CloudFormation, construir/publicar artefactos, crear un change set sin ejecutarlo y usar jobs manuales para QA/UAT/PROD, health-check y rollback manual.
- No ejecutes despliegues desde este pedido ni incluyas comandos destructivos fuera de jobs manuales.

## deployment_spec aprobado
{json.dumps(spec, ensure_ascii=False, indent=2)}

## deliverables de Desarrollo
{json.dumps(artifacts, ensure_ascii=False, indent=2)}

## Patrones corporativos de referencia
{library.context_for(design)}
"""


def _extract_generated_blocks(response: str) -> tuple[str, str]:
    def block(name: str) -> str:
        start, end = f"<{name}>", f"</{name}>"
        if start not in response or end not in response:
            raise InfrastructureGenerationError(f"la respuesta no contiene el bloque {name}")
        return response.split(start, 1)[1].split(end, 1)[0].strip()
    return block("cloudformation"), block("gitlab_ci")


def validate_generated_iac(cloudformation: str, gitlab_ci: str) -> None:
    """Validación local antes de permitir que el bundle llegue a revisión humana."""
    try:
        cf = yaml.safe_load(cloudformation)
        ci = yaml.safe_load(gitlab_ci)
    except yaml.YAMLError as exc:
        raise InfrastructureGenerationError(f"YAML generado inválido: {exc}") from exc
    if not isinstance(cf, dict) or not isinstance(cf.get("Resources"), dict) or not cf["Resources"]:
        raise InfrastructureGenerationError("CloudFormation debe declarar al menos un recurso")
    serialized = yaml.safe_dump(cf)
    if "AWS::Include" in serialized or "Fn::Transform" in serialized:
        raise InfrastructureGenerationError("CloudFormation no puede incluir transformaciones externas")
    if not isinstance(ci, dict) or not isinstance(ci.get("stages"), list):
        raise InfrastructureGenerationError("GitLab CI debe declarar stages")
    required_stages = {"test", "versionador", "build", "deploy_QA", "deploy_PROD"}
    if not required_stages.issubset(set(ci["stages"])):
        raise InfrastructureGenerationError("GitLab CI no contiene las etapas corporativas mínimas")
    deploy_jobs = [job for name, job in ci.items() if name.startswith("deploy_") and isinstance(job, dict)]
    if not deploy_jobs or any(job.get("when") != "manual" for job in deploy_jobs):
        raise InfrastructureGenerationError("los jobs de despliegue deben ser manuales")


def bedrock_iac_generator(prompt: str) -> str:
    """Generador opcional: Bedrock propone; las validaciones y aprobaciones conservan el control."""
    from delivery_crew.bedrock import ask
    return ask(prompt, max_tokens=8000)


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


def generate_bundle(
    store: RunStore, design: Design, change: Change, deployment: Deployment,
    profiles: list[str], generator: IacGenerator | None = None,
) -> Path:
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

    if generator:
        cloudformation_yaml, pipeline = _extract_generated_blocks(generator(build_iac_prompt(design, change)))
        validate_generated_iac(cloudformation_yaml, pipeline)
        target = cloudformation / "stack.yml"
        target.write_text(cloudformation_yaml + "\n", encoding="utf-8")
        (bundle / ".gitlab-ci-sysops.yml").write_text(pipeline + "\n", encoding="utf-8")
        shutil.copyfile(TEMPLATE_ROOT / "health-check-http.sh", scripts / "health-check-http.sh")
        manifest = {
            "run_id": deployment.run_id,
            "source_branch": change.branch,
            "architecture_decision": design.decision,
            "deployment_spec": design.deployment_spec.model_dump(mode="json") if design.deployment_spec else None,
            "deliverables": [artifact.model_dump(mode="json") for artifact in change.deliverables],
            "target_account_id": deployment.target_account_id,
            "region": deployment.region,
            "template_profiles": profiles,
            "generation_mode": "bedrock_with_template_context",
            "cloudformation_templates": ["cloudformation/stack.yml"],
            "pipeline": ".gitlab-ci-sysops.yml",
            "health_check": "scripts/health-check-http.sh",
            "required_ci_variables": ["AWS_DEFAULT_REGION", "CF_STACK_NAME", "HEALTHCHECK_URL", "PREVIOUS_APPROVED_TEMPLATE"],
            "status": "pending_sysops_approval",
        }
        (bundle / "manifest.yml").write_text(
            yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        store.audit("agente-despliegue", "deployment_bundle_generated", profiles=profiles,
                    mode="bedrock_with_template_context", bundle=str(bundle))
        return bundle

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


def create_plan(
    run_id: str, target_account_id: str, region: str = "us-west-2", base_dir: str = "runs",
    generator: IacGenerator | None = None,
) -> Deployment:
    """Create step 04 only when the developer's step 03 is human-approved."""
    store = RunStore(run_id, base_dir=base_dir)
    design = store.read(Design)
    if design.approval.status != "aprobado":
        raise NotApprovedError("02-diseno.md no está aprobado; SysOps no puede elegir infraestructura")
    change = store.read_input_for(4, Change)
    spec = design.deployment_spec
    if not spec:
        raise ValueError("el diseño no contiene deployment_spec estructurado")
    # El modo generativo puede usar todos los patrones como contexto, incluso si el recurso
    # solicitado no estaba previamente normalizado en el catálogo.
    profiles = (
        sorted(TemplateLibrary().search({component.kind for component in spec.components}))
        if generator else select_template_profiles(design)
    )
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
    bundle = generate_bundle(store, design, change, deployment, profiles, generator=generator)
    store.audit("agente-despliegue", "deployment_plan_created", source_branch=change.branch)
    return deployment


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genera 04-despliegue.md desde un 03-cambio.md aprobado.")
    parser.add_argument("run_id")
    parser.add_argument("--target-account", required=True)
    parser.add_argument("--region", default="us-west-2")
    parser.add_argument("--runs-dir", default="runs")
    parser.add_argument(
        "--generate-with-bedrock", action="store_true",
        help="generar CloudFormation y GitLab CI desde el contrato y los patrones revisados",
    )
    args = parser.parse_args(argv)
    try:
        plan = create_plan(
            args.run_id, args.target_account, args.region, args.runs_dir,
            generator=bedrock_iac_generator if args.generate_with_bedrock else None,
        )
    except (FileNotFoundError, NotApprovedError, ValueError) as exc:
        print(f"No se pudo generar el plan: {exc}", file=sys.stderr)
        return 2
    print(f"Plan generado: {RunStore(args.run_id, args.runs_dir).path / plan.FILENAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
