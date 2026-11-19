from pathlib import Path

import pytest

from delivery_crew.agents.deployment import create_plan
from delivery_crew.contracts import Change, DeployableArtifact, DeploymentComponent, DeploymentSpec, Design
from delivery_crew.runs import NotApprovedError, RunStore


def test_deployment_agent_requires_approved_change(tmp_path: Path):
    store = RunStore("demo-001", tmp_path).create()
    store.write(_design())
    store.decide(Design, "aprobado", by="arquitecto")
    store.write(Change(run_id="demo-001", branch="feature/code-65", files_modified=["src/rules.py"], test_result="passed", test_summary="12 passed"))
    with pytest.raises(NotApprovedError):
        create_plan("demo-001", "123456789012", base_dir=str(tmp_path))


def test_deployment_agent_writes_contract_and_audit(tmp_path: Path):
    store = RunStore("demo-001", tmp_path).create()
    store.write(_design())
    store.decide(Design, "aprobado", by="arquitecto")
    store.write(_change())
    store.decide(Change, "aprobado", by="desarrollador")
    deployment = create_plan("demo-001", "123456789012", base_dir=str(tmp_path))
    assert deployment.approval.status == "pendiente"
    assert store.read(type(deployment)).target_account_id == "123456789012"
    assert "lambda_dynamodb" in deployment.body
    assert any(entry["action"] == "deployment_plan_created" for entry in store.read_audit())
    bundle = store.path / "generated"
    assert (bundle / "cloudformation" / "lambda-dynamodb.yml").is_file()
    assert (bundle / ".gitlab-ci-sysops.yml").is_file()
    assert (bundle / "scripts" / "health-check-authorize.sh").is_file()
    assert "pending_sysops_approval" in (bundle / "manifest.yml").read_text(encoding="utf-8")


def test_deployment_agent_rejects_unknown_architecture_component(tmp_path: Path):
    store = RunStore("demo-001", tmp_path).create()
    design = _design()
    design.deployment_spec.components.append(DeploymentComponent(name="ledger", kind="rds"))
    store.write(design)
    store.decide(Design, "aprobado", by="arquitecto")
    store.write(_change())
    store.decide(Change, "aprobado", by="desarrollador")
    with pytest.raises(ValueError, match="no hay perfil homologado"):
        create_plan("demo-001", "123456789012", base_dir=str(tmp_path))


def test_deployment_agent_rejects_missing_compute_artifact(tmp_path: Path):
    store = RunStore("demo-001", tmp_path).create()
    store.write(_design())
    store.decide(Design, "aprobado", by="arquitecto")
    change = _change()
    change.deliverables = []
    store.write(change)
    store.decide(Change, "aprobado", by="desarrollador")
    with pytest.raises(ValueError, match="no entregó artefactos"):
        create_plan("demo-001", "123456789012", base_dir=str(tmp_path))


def test_deployment_agent_can_generate_custom_iac_from_template_context(tmp_path: Path):
    """A component without a closed profile can be generated, pending human approval."""
    store = RunStore("demo-001", tmp_path).create()
    design = _design()
    design.deployment_spec.components.append(DeploymentComponent(name="ledger", kind="rds"))
    store.write(design)
    store.decide(Design, "aprobado", by="arquitecto")
    store.write(_change())
    store.decide(Change, "aprobado", by="desarrollador")

    deployment = create_plan("demo-001", "123456789012", base_dir=str(tmp_path), generator=_generated_iac)

    generated = store.path / "generated"
    assert deployment.approval.status == "pendiente"
    assert "AWS::RDS::DBInstance" in (generated / "cloudformation" / "stack.yml").read_text(encoding="utf-8")
    assert "bedrock_with_template_context" in (generated / "manifest.yml").read_text(encoding="utf-8")


def _generated_iac(_prompt: str) -> str:
    return """<cloudformation>
AWSTemplateFormatVersion: '2010-09-09'
Resources:
  Ledger:
    Type: AWS::RDS::DBInstance
    Properties:
      DBInstanceClass: db.t3.micro
      Engine: postgres
</cloudformation>
<gitlab_ci>
stages: [test, versionador, build, deploy, deploy_QA, deploy_UAT, deploy_PROD]
validate:
  stage: test
  script: [echo validate]
deploy_qa:
  stage: deploy_QA
  when: manual
  script: [echo deploy]
deploy_prod:
  stage: deploy_PROD
  when: manual
  script: [echo deploy]
</gitlab_ci>"""


def _design() -> Design:
    return Design(
        run_id="demo-001", summary="Usar servicio administrado.", components=["auth-service", "DynamoDB"],
        decision="DynamoDB con TTL", verdict="aprobado",
        deployment_spec=DeploymentSpec(
            environment="qa", network_exposure="public", data_classification="synthetic",
            health_check="POST /authorize", rollback_strategy="Restaurar una versión de Lambda aprobada.",
            observability=["CloudWatch logs"],
            components=[
                DeploymentComponent(name="api", kind="api_gateway"),
                DeploymentComponent(name="handler", kind="lambda"),
                DeploymentComponent(name="frequency", kind="dynamodb"),
            ],
        ),
    )


def _change() -> Change:
    return Change(
        run_id="demo-001", branch="feature/code-65", files_modified=["src/rules.py"],
        test_result="passed", test_summary="12 passed",
        deliverables=[DeployableArtifact(component="handler", kind="zip", source_path="services/auth_service", build_command="zip -r artifact.zip .")],
    )
