from pathlib import Path

import pytest

from delivery_crew.agents.deployment import create_plan
from delivery_crew.contracts import Change, Design
from delivery_crew.runs import NotApprovedError, RunStore


def test_deployment_agent_requires_approved_change(tmp_path: Path):
    store = RunStore("demo-001", tmp_path).create()
    store.write(Design(run_id="demo-001", summary="Usar servicio administrado.", components=["auth-service", "DynamoDB"], decision="DynamoDB con TTL", verdict="aprobado"))
    store.decide(Design, "aprobado", by="arquitecto")
    store.write(Change(run_id="demo-001", branch="feature/code-65", files_modified=["src/rules.py"], test_result="passed", test_summary="12 passed"))
    with pytest.raises(NotApprovedError):
        create_plan("demo-001", "123456789012", base_dir=str(tmp_path))


def test_deployment_agent_writes_contract_and_audit(tmp_path: Path):
    store = RunStore("demo-001", tmp_path).create()
    store.write(Design(run_id="demo-001", summary="Usar servicio administrado.", components=["auth-service", "DynamoDB"], decision="DynamoDB con TTL", verdict="aprobado"))
    store.decide(Design, "aprobado", by="arquitecto")
    store.write(Change(run_id="demo-001", branch="feature/code-65", files_modified=["src/rules.py"], test_result="passed", test_summary="12 passed"))
    store.decide(Change, "aprobado", by="desarrollador")
    deployment = create_plan("demo-001", "123456789012", base_dir=str(tmp_path))
    assert deployment.approval.status == "pendiente"
    assert store.read(type(deployment)).target_account_id == "123456789012"
    assert "lambda_dynamodb" in deployment.body
    assert any(entry["action"] == "deployment_plan_created" for entry in store.read_audit())
