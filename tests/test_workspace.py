"""Modo repo de GitHub: validación de la URL, clonado, detección del paquete, agentes sobre el clon y PR."""

import shutil
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from delivery_crew import examples, orchestrator as orch, workspace as ws
from delivery_crew.agents.deployment import create_plan
from delivery_crew.agents.developer import run_developer
from delivery_crew.api.app import create_app
from delivery_crew.contracts import Change, Design, Requirement
from delivery_crew.runs import RunStore

ROOT = Path(__file__).resolve().parents[1]
BRANCH = "feature/usuario-desplegar-la-api-de-comercios-con-persis"
REPO_URL = "https://github.com/tomasdemarco/api-demo-agentic-ambassadors"


def git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True,
                          capture_output=True, text=True, encoding="utf-8").stdout.strip()


@pytest.fixture
def source_repo(tmp_path):
    """Un repo como el de la demo: el servicio es la raíz (paquete merchants_api/, tests/, smoke.json)."""
    root = tmp_path / "origen"
    shutil.copytree(ROOT / "services" / "merchants_api", root,
                    ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    (root / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")
    return root


# --- URL ---------------------------------------------------------------------

@pytest.mark.parametrize("url,expected", [
    (REPO_URL, ("tomasdemarco", "api-demo-agentic-ambassadors")),
    (REPO_URL + ".git", ("tomasdemarco", "api-demo-agentic-ambassadors")),
    (REPO_URL + "/", ("tomasdemarco", "api-demo-agentic-ambassadors")),
    ("https://github.com/Giul00/agentic-ambassadors-project", ("Giul00", "agentic-ambassadors-project")),
])
def test_valid_urls(url, expected):
    ref = ws.parse_repo_url(url)
    assert (ref.owner, ref.name) == expected
    assert ref.url == f"https://github.com/{expected[0]}/{expected[1]}.git"


@pytest.mark.parametrize("url", [
    "http://github.com/tomasdemarco/x",
    "git@github.com:tomasdemarco/x.git",
    "https://gitlab.com/tomasdemarco/x",
    "https://github.com/tomasdemarco/../x",
    "https://github.com/tomasdemarco/x?ref=y",
    "file:///etc/passwd",
    "https://github.com/tomasdemarco",
    "",
])
def test_invalid_urls(url):
    with pytest.raises(ws.WorkspaceError):
        ws.parse_repo_url(url)


def test_owner_must_be_allowed(monkeypatch):
    with pytest.raises(ws.WorkspaceError, match="no está en la lista permitida"):
        ws.parse_repo_url("https://github.com/otra-org/repo")
    monkeypatch.setenv("DELIVERY_CREW_GITHUB_OWNERS", "otra-org")
    assert ws.parse_repo_url("https://github.com/otra-org/repo").owner == "otra-org"


# --- clonado y paquete ----------------------------------------------------------

def test_clone_and_detect_package(tmp_path, source_repo):
    dest = tmp_path / "run" / "workspace"
    commit = ws.clone(ws.parse_repo_url(REPO_URL), None, dest, source=str(source_repo))
    assert len(commit) == 12 and (dest / "merchants_api" / "handler.py").is_file()
    assert ws.detect_package(dest) == "merchants_api"


def test_repo_with_submodules_is_rejected(tmp_path, source_repo):
    (source_repo / ".gitmodules").write_text("[submodule \"x\"]\n", encoding="utf-8")
    git(source_repo, "add", "-A")
    git(source_repo, "commit", "-q", "-m", "sub")
    with pytest.raises(ws.WorkspaceError, match="submódulos"):
        ws.clone(ws.parse_repo_url(REPO_URL), None, tmp_path / "w", source=str(source_repo))


def test_detect_package_errors(tmp_path):
    (tmp_path / "a").mkdir()
    with pytest.raises(ws.WorkspaceError, match="no se encontró"):
        ws.detect_package(tmp_path)
    for name in ("uno", "dos"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "handler.py").write_text("def lambda_handler(e, c):\n    pass\n", encoding="utf-8")
    with pytest.raises(ws.WorkspaceError, match="más de un paquete"):
        ws.detect_package(tmp_path)


def test_invalid_ref_is_rejected(tmp_path):
    with pytest.raises(ws.WorkspaceError, match="rama"):
        ws.clone(ws.parse_repo_url(REPO_URL), "../main", tmp_path / "w")


def test_token_is_scrubbed_from_errors(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_SECRETO123")
    assert "ghp_SECRETO123" not in ws._scrub("fatal: https://ghp_SECRETO123@github.com falló")
    assert any("extraheader" in a for a in ws._auth_args())
    assert all("ghp_SECRETO123" not in a for a in ws._auth_args())


# --- agentes sobre el clon --------------------------------------------------------

@pytest.fixture
def repo_run(tmp_path, source_repo):
    store = RunStore("repo-run", tmp_path / "runs").create()
    req = examples.merchants_requirement("repo-run").model_copy(update={"source_repo": REPO_URL})
    ws.prepare(req, store.path, source=str(source_repo))
    store.write(req)
    store.write(examples.merchants_design("repo-run"))
    return store


def adapter_agent(sandbox):
    def run(prompt):
        run.prompt = prompt
        sandbox.read_file("merchants_api/ports.py")
        sandbox.write_file("merchants_api/adapters/dynamodb.py", "class DynamoDBMerchantRepository:\n    pass\n")
        sandbox.write_file("tests/test_dynamodb_adapter.py", "def test_x():\n    assert True\n")
        return "Agregué el adaptador DynamoDB."
    return run


def test_developer_works_on_the_clone_and_declares_root_deliverable(repo_run, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    captured = {}

    def factory(sandbox):
        captured["agent"] = adapter_agent(sandbox)
        return captured["agent"]

    change = run_developer(repo_run, ROOT, agent_factory=factory)
    assert change.test_result == "passed"
    assert set(change.files_modified) == {"merchants_api/adapters/dynamodb.py", "tests/test_dynamodb_adapter.py"}
    d = change.deliverables[0]
    assert (d.source_path, d.entrypoint) == (".", "merchants_api.handler.lambda_handler")
    assert "Handler: merchants_api.handler.lambda_handler" in captured["agent"].prompt
    assert "'id'" in captured["agent"].prompt and "STORAGE_BACKEND=dynamodb" in captured["agent"].prompt
    # Sin token: no hay PR, y queda registrado por qué.
    assert change.pull_request_url is None
    skipped = [e for e in repo_run.read_audit() if e["action"] == "pull_request_skipped"]
    assert skipped and "GITHUB_TOKEN" in skipped[0]["reason"]
    # El commit queda en el clon, no en este repositorio.
    clone = ws.workspace_path(repo_run.path)
    assert "merchants_api/adapters/dynamodb.py" in git(clone, "show", "--name-only", "--format=", BRANCH)
    assert git(ROOT, "branch", "--list", BRANCH) == ""

    # El plan de despliegue entiende el entregable en la raíz del clon.
    repo_run.decide(Change, "aprobado", by="tomas")
    dep = create_plan("repo-run", "123456789012", base_dir=str(repo_run.path.parent))
    assert dep.stack_name == "dc-merchants-api-qa"
    pipeline = (repo_run.path / "generated" / ".gitlab-ci-sysops.yml").read_text(encoding="utf-8")
    assert "SERVICE_DIR: ." in pipeline and "SERVICE_PACKAGE: merchants_api" in pipeline


def test_executor_packages_from_the_clone(repo_run, monkeypatch):
    from delivery_crew.agents import deploy_executor as ex

    run_developer(repo_run, ROOT, agent_factory=adapter_agent)
    data, commit = ex.package_from_branch(ws.workspace_path(repo_run.path), BRANCH, ".", "merchants_api")
    import io
    import zipfile

    names = zipfile.ZipFile(io.BytesIO(data)).namelist()
    assert "merchants_api/adapters/dynamodb.py" in names and not any(n.startswith("tests/") for n in names)


def test_pull_request_is_opened_with_token(repo_run, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_prueba")
    pushed, calls = [], []
    real_git = ws.git

    def fake_git(cwd, *args, auth=False, check=True):
        if args and args[0] == "push":
            pushed.append((args, auth))
            return ""
        return real_git(cwd, *args, check=check)

    monkeypatch.setattr(ws, "git", fake_git)

    def fake_api(method, url, body, token):
        calls.append((method, url, body, token))
        return 201, {"html_url": "https://github.com/tomasdemarco/api-demo-agentic-ambassadors/pull/1"}

    import delivery_crew.agents.developer as dev
    monkeypatch.setattr(dev, "push_and_open_pr",
                        lambda loc, wt, br, title, body: ws.push_and_open_pr(loc, wt, br, title, body, api=fake_api))
    change = run_developer(repo_run, ROOT, agent_factory=adapter_agent)

    assert change.pull_request_url.endswith("/pull/1")
    (args, auth), = pushed
    assert auth is True and args[2].endswith("api-demo-agentic-ambassadors.git")
    assert args[3] == f"{BRANCH}:refs/heads/{BRANCH}"
    method, url, body, token = calls[0]
    assert method == "POST" and url.endswith("/repos/tomasdemarco/api-demo-agentic-ambassadors/pulls")
    assert body["head"] == BRANCH and body["base"] == "main" and token == "ghp_prueba"
    assert "Delivery Crew" in body["title"] and "ARQ-08" in body["body"]
    # El token no queda escrito en ningún artefacto ni en la auditoría.
    for f in repo_run.path.glob("*.md"):
        assert "ghp_prueba" not in f.read_text(encoding="utf-8")
    assert "ghp_prueba" not in repo_run.audit_path.read_text(encoding="utf-8")


def _fake_github(monkeypatch, merge_status=200):
    """GitHub simulado: push sin red, apertura de PR y merge."""
    import delivery_crew.agents.developer as dev

    monkeypatch.setenv("GITHUB_TOKEN", "ghp_prueba")
    calls = []
    real_git = ws.git

    def fake_git(cwd, *args, auth=False, check=True):
        if args and args[0] == "push":
            calls.append(("push", args[3]))
            return ""
        return real_git(cwd, *args, check=check)

    def api(method, url, body, token):
        calls.append((method, url.split("/repos/")[1], body))
        if method == "POST":
            return 201, {"html_url": "https://github.com/tomasdemarco/api-demo-agentic-ambassadors/pull/7"}
        if merge_status == 200:
            return 200, {"merged": True, "sha": "abcdef1234567890abcdef1234567890abcdef12"}
        return merge_status, {"message": "Head branch was modified. Review and try the merge again."}

    monkeypatch.setattr(ws, "git", fake_git)
    monkeypatch.setattr(dev, "push_and_open_pr",
                        lambda loc, wt, br, title, body: ws.push_and_open_pr(loc, wt, br, title, body, api=api))
    monkeypatch.setattr(dev, "merge_pull_request",
                        lambda loc, br, url, title: ws.merge_pull_request(loc, br, url, title, api=api))
    return calls


def test_approved_change_is_merged_with_the_approved_commit(repo_run, monkeypatch):
    from delivery_crew.agents.developer import integrate_change

    calls = _fake_github(monkeypatch)
    run_developer(repo_run, ROOT, agent_factory=adapter_agent)
    repo_run.decide(Change, "aprobado", by="tomas")
    change = integrate_change(repo_run, ROOT)

    assert change.merge_commit == "abcdef1234567890abcdef1234567890abcdef12"
    merge = [c for c in calls if c[0] == "PUT"][0]
    assert merge[1].endswith("/pulls/7/merge")
    approved = git(ws.workspace_path(repo_run.path), "rev-parse", BRANCH)
    assert merge[2]["sha"] == approved and merge[2]["merge_method"] == "squash"
    assert repo_run.read(Change).approval.status == "aprobado"  # sigue aprobado tras registrar el merge
    assert any(e["action"] == "pull_request_merged" for e in repo_run.read_audit())
    # Idempotente: no vuelve a mergear.
    integrate_change(repo_run, ROOT)
    assert len([c for c in calls if c[0] == "PUT"]) == 1


def test_change_is_not_integrated_before_approval(repo_run, monkeypatch):
    from delivery_crew.agents.developer import integrate_change
    from delivery_crew.runs import NotApprovedError

    _fake_github(monkeypatch)
    run_developer(repo_run, ROOT, agent_factory=adapter_agent)
    with pytest.raises(NotApprovedError):
        integrate_change(repo_run, ROOT)


def test_branch_modified_after_approval_blocks_the_merge(repo_run, monkeypatch):
    from delivery_crew.agents.developer import DeveloperError, integrate_change

    _fake_github(monkeypatch, merge_status=409)
    run_developer(repo_run, ROOT, agent_factory=adapter_agent)
    repo_run.decide(Change, "aprobado", by="tomas")
    with pytest.raises(DeveloperError, match="cambió después de la aprobación"):
        integrate_change(repo_run, ROOT)
    assert repo_run.read(Change).merge_commit is None


def test_without_token_the_flow_continues_without_merge(repo_run, monkeypatch):
    from delivery_crew.agents.developer import integrate_change

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    run_developer(repo_run, ROOT, agent_factory=adapter_agent)
    repo_run.decide(Change, "aprobado", by="tomas")
    change = integrate_change(repo_run, ROOT)
    assert change.merge_commit is None
    assert any(e["action"] == "merge_skipped" for e in repo_run.read_audit())


def test_local_code_is_not_merged(tmp_path):
    from delivery_crew.agents.developer import integrate_change

    s = RunStore("local", tmp_path).create()
    s.write(examples.requirement("local"))
    s.write(examples.design("local"))
    s.write(examples.change("local"))
    change = integrate_change(s, ROOT)
    assert change.merge_commit is None
    assert [e for e in s.read_audit() if e["action"] == "merge_skipped"]


def test_developer_with_relative_runs_dir_and_long_run_id(tmp_path, source_repo, monkeypatch):
    """Regresión: la API usa runs/ relativo; git resolvía la ruta desde el clon y la duplicaba."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    run_id = orch.make_run_id("Desplegar la API de comercios con persistencia real")
    store = RunStore(run_id, "runs").create()
    req = examples.merchants_requirement(run_id).model_copy(update={"source_repo": REPO_URL})
    ws.prepare(req, store.path, source=str(source_repo))
    store.write(req)
    store.write(examples.merchants_design(run_id))
    change = run_developer(store, ROOT, agent_factory=adapter_agent)
    assert change.test_result == "passed"
    wt = tmp_path / "runs" / run_id / "wt"
    assert (wt / "merchants_api" / "adapters" / "dynamodb.py").is_file()
    assert not (tmp_path / "runs" / run_id / "workspace" / "runs").exists()  # sin ruta duplicada
    assert len(run_id) <= 40


def test_branch_name_convention():
    from delivery_crew.agents.developer import branch_name

    assert branch_name("Tomás Demarco", "Agregar el campo email al comercio") == \
        "feature/tomas-demarco-agregar-el-campo-email-al-comercio"
    assert branch_name("", "") == "feature/agente-cambio"
    assert branch_name("x" * 50, "y" * 80) == "feature/" + "x" * 20 + "-" + "y" * 40


def test_existing_branch_gets_a_suffix(repo_run, monkeypatch):
    from delivery_crew.agents.developer import unique_branch

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    clone = ws.workspace_path(repo_run.path)
    git(clone, "branch", BRANCH)
    git(clone, "branch", BRANCH + "-2")
    monkeypatch.setattr(ws, "git", lambda *a, **k: (_ for _ in ()).throw(ws.WorkspaceError("sin red")))
    assert unique_branch(BRANCH, clone) == BRANCH + "-3"


def test_retry_after_rejection_reuses_the_same_branch(repo_run, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    first = run_developer(repo_run, ROOT, agent_factory=adapter_agent)
    repo_run.decide(Change, "rechazado", by="tomas", reason="falta una prueba")
    again = run_developer(repo_run, ROOT, agent_factory=adapter_agent, fresh=True)
    assert first.branch == again.branch == BRANCH


def test_architect_reads_the_clone(repo_run):
    from delivery_crew.agents.architect import DesignProposal, generate_design

    repo_run.write(examples.merchants_requirement("repo-run").model_copy(update={"source_repo": REPO_URL}))
    (repo_run.path / "02-diseno.md").unlink()
    seen = {}

    def fake(prompt):
        seen["prompt"] = prompt
        return DesignProposal(**examples.merchants_design().model_dump(
            include={"summary", "components", "decision", "risks", "verdict", "standards_cited", "deployment_spec"}))

    generate_design("repo-run", repo_run.path.parent, agent_fn=fake)
    assert "### merchants_api/ports.py" in seen["prompt"] and "class MerchantRepository" in seen["prompt"]
    assert "tests/" not in seen["prompt"].split("# Código actual")[1].split("Produce tu respuesta")[0].replace("tests/`", "")
    msgs = [e["text"] for e in repo_run.read_audit() if e["action"] == "agent_message"]
    assert any(REPO_URL in m for m in msgs)


# --- API ---------------------------------------------------------------------------

def test_api_creates_run_from_repo(tmp_path, source_repo):
    calls = []

    def factory():
        return orch.Agents(lambda s: calls.append(2), lambda s: None, lambda s: None)

    client = TestClient(create_app(tmp_path / "runs", agents_factory=factory, clone_source=str(source_repo)))
    r = client.post("/api/runs", json={**examples.MERCHANTS_REQUIREMENT, "requested_by": "tomas",
                                       "source_repo": REPO_URL + ".git", "affected_service": "auth-service"})
    assert r.status_code == 201, r.text
    req = r.json()["stages"][0]["artifact"]
    assert req["source_repo"] == REPO_URL and req["affected_service"] == "merchants-api"
    assert len(req["source_commit"]) == 12
    assert (tmp_path / "runs" / r.json()["run_id"] / "workspace" / "merchants_api").is_dir()
    deadline = time.monotonic() + 5
    while not calls and time.monotonic() < deadline:
        time.sleep(0.02)
    assert calls == [2]


def test_api_rejects_disallowed_repo_without_leaving_files(tmp_path):
    client = TestClient(create_app(tmp_path / "runs", agents_factory=lambda: None))
    r = client.post("/api/runs", json={**examples.MERCHANTS_REQUIREMENT, "requested_by": "t",
                                       "source_repo": "https://github.com/desconocido/repo"})
    assert r.status_code == 422 and "lista permitida" in r.text
    assert not any((tmp_path / "runs").glob("*/workspace"))


def test_config_reports_github_and_demo_repo(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    cfg = TestClient(create_app(tmp_path)).get("/api/config").json()
    assert cfg["github_token"] is False and cfg["demo_repo"] == REPO_URL
    assert "tomasdemarco" in [o.lower() for o in cfg["allowed_owners"]]
