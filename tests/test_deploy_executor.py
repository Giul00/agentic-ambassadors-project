"""Ejecutor de despliegue con AWS simulado: change set, eventos, outputs y prueba de humo."""

import io
import json
import shutil
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from delivery_crew import examples, orchestrator as orch
from delivery_crew.agents import deploy_executor as ex
from delivery_crew.agents.deployment import create_plan
from delivery_crew.contracts import Change, DeployableArtifact, Deployment
from delivery_crew.conventions import build_command, lambda_entrypoint, service_dir
from delivery_crew.runs import NotApprovedError, RunStore

ROOT = Path(__file__).resolve().parents[1]
ACCOUNT = "123456789012"
URL = "https://abc123.execute-api.us-west-2.amazonaws.com/qa"


def git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True,
                          capture_output=True, text=True, encoding="utf-8").stdout.strip()


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    shutil.copytree(ROOT / "services" / "merchants_api", root / "services" / "merchants_api",
                    ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    (root / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")
    git(root, "branch", "agente/run-x")
    return root


@pytest.fixture
def store(tmp_path, repo):
    s = RunStore("run-x", tmp_path / "runs").create()
    s.write(examples.merchants_requirement("run-x"))
    s.write(examples.merchants_design("run-x"))
    s.write(Change(run_id="run-x", branch="agente/run-x", files_modified=["services/merchants_api/x.py"],
                   test_result="passed", test_summary="ok",
                   deliverables=[DeployableArtifact(component="merchants-handler", kind="zip",
                                                    source_path=service_dir("merchants-api"),
                                                    build_command=build_command("merchants-api"),
                                                    entrypoint=lambda_entrypoint("merchants-api"))]))
    s.decide(Change, "aprobado", by="tomas")
    create_plan("run-x", ACCOUNT, base_dir=str(s.path.parent))
    s.decide(Deployment, "aprobado", by="sysops")
    return s


class FakeAWS:
    def __init__(self, account=ACCOUNT, final="CREATE_COMPLETE", no_changes=False, existing=None):
        self.account, self.final, self.no_changes = account, final, no_changes
        self.status = existing
        self.calls = []
        self.objects = {}
        self.change_set = None
        self.polls = 0

    def __call__(self, name):
        return self

    # sts
    def get_caller_identity(self):
        return {"Account": self.account}

    # s3
    def head_bucket(self, Bucket):
        self.calls.append(("head_bucket", Bucket))
        raise RuntimeError("404")

    def create_bucket(self, Bucket, **kw):
        self.calls.append(("create_bucket", Bucket))

    def put_public_access_block(self, **kw):
        self.calls.append(("put_public_access_block",))

    def put_bucket_encryption(self, **kw):
        self.calls.append(("put_bucket_encryption",))

    def put_object(self, Bucket, Key, Body, **kw):
        self.objects[(Bucket, Key)] = Body

    # cloudformation
    def describe_stacks(self, StackName):
        if self.status is None:
            raise RuntimeError(f"Stack with id {StackName} does not exist")
        if self.status == "CREATE_IN_PROGRESS":
            self.polls += 1
            if self.polls >= 2:
                self.status = self.final
        outputs = [{"OutputKey": "ApiUrl", "OutputValue": URL}] if self.status in ex.TERMINAL_OK else []
        return {"Stacks": [{"StackStatus": self.status, "Outputs": outputs}]}

    def create_change_set(self, **kw):
        self.change_set = kw
        if self.status is None:
            self.status = "REVIEW_IN_PROGRESS"

    def describe_change_set(self, StackName, ChangeSetName):
        if self.no_changes:
            return {"Status": "FAILED", "StatusReason": "The submitted information didn't contain changes."}
        return {"Status": "CREATE_COMPLETE", "Changes": [
            {"ResourceChange": {"Action": "Add", "ResourceType": "AWS::DynamoDB::Table", "LogicalResourceId": "Table"}},
            {"ResourceChange": {"Action": "Add", "ResourceType": "AWS::Lambda::Function", "LogicalResourceId": "Function"}},
        ]}

    def execute_change_set(self, **kw):
        self.status = "CREATE_IN_PROGRESS"

    def describe_stack_events(self, StackName):
        now = datetime.now(timezone.utc)
        events = [{"EventId": "1", "LogicalResourceId": "Table", "ResourceType": "AWS::DynamoDB::Table",
                   "ResourceStatus": "CREATE_COMPLETE", "Timestamp": now}]
        if self.final == "ROLLBACK_COMPLETE":
            events.append({"EventId": "2", "LogicalResourceId": "Api", "ResourceType": "AWS::ApiGateway::RestApi",
                           "ResourceStatus": "CREATE_FAILED", "ResourceStatusReason": "AccessDenied apigateway:PUT",
                           "Timestamp": now})
        return {"StackEvents": events}

    def delete_stack(self, StackName):
        self.calls.append(("delete_stack", StackName))
        self.status = None


def api_http(monkeypatch, healthy_storage="dynamodb"):
    """La API desplegada, simulada con el handler real del servicio en memoria."""
    import sys
    sys.path.insert(0, str(ROOT / "services" / "merchants_api"))
    from merchants_api import handler
    from merchants_api.adapters.memory import InMemoryMerchantRepository
    from merchants_api.service import MerchantService

    handler.reset_service(MerchantService(InMemoryMerchantRepository()))
    monkeypatch.setenv("STORAGE_BACKEND", healthy_storage)
    requests = []

    def http(method, url, body):
        assert url.startswith(URL)
        requests.append((method, url[len(URL):]))
        r = handler.lambda_handler({"httpMethod": method, "path": url[len(URL):],
                                    "body": body.decode() if body else None})
        return r["statusCode"], r["body"]

    http.requests = requests
    return http


def run(store, repo, aws, http):
    return ex.execute_deployment(store, repo, clients=aws, http=http, sleep=lambda s: None, poll_seconds=0)


def test_successful_deployment(store, repo, monkeypatch):
    aws, http = FakeAWS(), api_http(monkeypatch)
    dep = run(store, repo, aws, http)

    assert dep.deployment_status == "desplegado" and dep.health_check == "ok"
    assert dep.endpoint_url == URL and dep.approval.status == "aprobado"
    commit = git(repo, "rev-parse", "--short=12", "agente/run-x")
    assert dep.deployed_commit == commit

    # Código del commit aprobado, sin pruebas.
    (bucket, key), body = next(iter(aws.objects.items()))
    assert bucket == f"delivery-crew-artifacts-{ACCOUNT}-us-west-2" and commit in key
    names = zipfile.ZipFile(io.BytesIO(body)).namelist()
    assert "merchants_api/handler.py" in names and not any("tests/" in n for n in names)
    assert ("put_public_access_block",) in aws.calls and ("put_bucket_encryption",) in aws.calls

    # Parámetros del deployment_spec (Arquitectura) y del entregable (Desarrollo).
    params = {p["ParameterKey"]: p["ParameterValue"] for p in aws.change_set["Parameters"]}
    assert params["TablePartitionKey"] == "id"
    assert params["StorageBackend"] == "dynamodb"
    assert params["LambdaHandler"] == "merchants_api.handler.lambda_handler"
    assert params["ProjectName"] == "dc-merchants-api" and params["Environment"] == "qa"
    assert aws.change_set["StackName"] == "dc-merchants-api-qa" and aws.change_set["ChangeSetType"] == "CREATE"
    assert "Tags" not in aws.change_set  # sin tags a nivel de stack (el workshop no permite etiquetar API Gateway)

    # Prueba de humo completa.
    assert [m for m, _ in http.requests] == ["GET", "POST", "GET", "PUT", "GET", "DELETE", "GET"]
    progress = [e["text"] for e in store.read_audit() if e["action"] == "deploy_progress"]
    assert any("Change set (CREATE) con 2 cambios" in p for p in progress)
    assert any("AWS::DynamoDB::Table Table: CREATE_COMPLETE" in p for p in progress)
    assert any("✓ alta" in p for p in progress)


def test_account_mismatch_stops_before_touching_aws(store, repo, monkeypatch):
    aws = FakeAWS(account="999999999999")
    with pytest.raises(ex.DeployError, match="la cuenta activa es 999999999999"):
        run(store, repo, aws, api_http(monkeypatch))
    assert aws.objects == {} and aws.change_set is None
    assert store.read(Deployment).deployment_status == "fallido"


def test_requires_sysops_approval(tmp_path, repo):
    s = RunStore("sin-ok", tmp_path / "runs").create()
    s.write(examples.merchants_requirement("sin-ok"))
    s.write(examples.merchants_design("sin-ok"))
    s.write(examples.change("sin-ok"))
    s.write(examples.deployment("sin-ok", approved=False))
    with pytest.raises(NotApprovedError):
        ex.execute_deployment(s, repo, clients=FakeAWS())


def test_stack_failure_is_reported_with_reason(store, repo, monkeypatch):
    aws = FakeAWS(final="ROLLBACK_COMPLETE")
    with pytest.raises(ex.DeployError, match="AccessDenied apigateway:PUT"):
        run(store, repo, aws, api_http(monkeypatch))
    dep = store.read(Deployment)
    assert dep.deployment_status == "fallido" and dep.health_check == "fallo"


def test_failed_empty_stack_is_recreated(store, repo, monkeypatch):
    aws = FakeAWS(existing="ROLLBACK_COMPLETE")
    dep = run(store, repo, aws, api_http(monkeypatch))
    assert ("delete_stack", "dc-merchants-api-qa") in aws.calls and dep.deployment_status == "desplegado"


def test_smoke_failure_marks_deployment_failed(store, repo, monkeypatch):
    dep = run(store, repo, FakeAWS(), api_http(monkeypatch, healthy_storage="memory"))
    assert dep.deployment_status == "fallido" and dep.health_check == "fallo"
    assert any("storage='memory' (se esperaba 'dynamodb')" in line for line in dep.deployment_log)


def test_no_changes_still_runs_smoke(store, repo, monkeypatch):
    aws = FakeAWS(existing="UPDATE_COMPLETE", no_changes=True)
    dep = run(store, repo, aws, api_http(monkeypatch))
    assert dep.deployment_status == "desplegado" and aws.change_set["ChangeSetType"] == "UPDATE"


def test_busy_stack_is_not_touched(store, repo, monkeypatch):
    aws = FakeAWS(existing="UPDATE_IN_PROGRESS")
    with pytest.raises(ex.DeployError, match="ocupado"):
        run(store, repo, aws, api_http(monkeypatch))
    assert aws.change_set is None


@pytest.mark.parametrize("bad", ["../secreto", "services/../../x", "a b"])
def test_package_rejects_unsafe_paths(repo, bad):
    with pytest.raises(ex.DeployError):
        ex.package_from_branch(repo, "agente/run-x", bad)


def test_run_smoke_substitutes_saved_values_and_stops_on_failure():
    calls = []

    def http(method, url, body):
        calls.append((method, url))
        if method == "POST":
            return 201, json.dumps({"id": "mer_000000000001"})
        return 500, "{}"

    spec = {"steps": [
        {"name": "alta", "method": "POST", "path": "/m", "body": {}, "expect_status": 201, "save": {"id": "id"}},
        {"name": "consulta", "method": "GET", "path": "/m/{id}", "expect_status": 200},
        {"name": "nunca", "method": "GET", "path": "/x"},
    ]}
    results = ex.run_smoke("https://h/qa/", spec, http=http)
    assert [r.ok for r in results] == [True, False]
    assert calls == [("POST", "https://h/qa/m"), ("GET", "https://h/qa/m/mer_000000000001")]
    assert "HTTP 500" in results[1].detail


# --- orquestador con ejecutor --------------------------------------------------

def test_orchestrator_runs_executor_after_plan_approval(tmp_path):
    s = RunStore("o", tmp_path)
    orch.start(s, examples.requirement("o", approved=False), requested_by="t")
    calls = []

    def executor(store):
        calls.append("deploy")
        d = store.read(Deployment)
        store.write(d.model_copy(update={"deployment_status": "desplegado", "endpoint_url": URL}))

    agents = orch.Agents(
        architect=lambda st: st.write(examples.design(st.run_id, approved=False)),
        developer=lambda st: st.write(examples.change(st.run_id, approved=False)),
        deployment=lambda st: st.write(examples.deployment(st.run_id, approved=False)),
        executor=executor,
    )
    approve = lambda st, step: st.decide(orch.ARTIFACTS[step - 1], "aprobado", by="x")
    result = orch.run(s, agents, decide=approve, log=lambda m: None)
    assert result.outcome == orch.COMPLETED and calls == ["deploy"]
    started = [e for e in s.read_audit() if e["action"] == "stage_started"]
    assert started[-1]["step"] == orch.EXECUTION_STEP


def test_orchestrator_reports_failed_deployment_and_can_retry(tmp_path):
    s = RunStore("o2", tmp_path)
    orch.start(s, examples.requirement("o2", approved=False), requested_by="t")
    attempts = []

    def executor(store):
        attempts.append(1)
        d = store.read(Deployment)
        if len(attempts) == 1:
            store.write(d.model_copy(update={"deployment_status": "fallido", "deployment_log": ["Error: credenciales"]}))
            raise RuntimeError("ExpiredToken")
        store.write(d.model_copy(update={"deployment_status": "desplegado"}))

    agents = orch.Agents(
        architect=lambda st: st.write(examples.design(st.run_id, approved=False)),
        developer=lambda st: st.write(examples.change(st.run_id, approved=False)),
        deployment=lambda st: st.write(examples.deployment(st.run_id, approved=False)),
        executor=executor,
    )
    approve = lambda st, step: st.decide(orch.ARTIFACTS[step - 1], "aprobado", by="x")
    first = orch.run(s, agents, decide=approve, log=lambda m: None)
    assert (first.outcome, first.step) == (orch.FAILED, orch.EXECUTION_STEP)
    again = orch.run(s, agents, decide=approve, log=lambda m: None)
    assert again.outcome == orch.FAILED and len(attempts) == 1  # sin --retry no reintenta solo
    retried = orch.run(s, agents, decide=approve, retry_rejected=True, log=lambda m: None)
    assert retried.outcome == orch.COMPLETED and len(attempts) == 2
