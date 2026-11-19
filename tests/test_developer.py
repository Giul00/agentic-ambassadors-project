"""Pruebas del flujo del agente Desarrollador con agentes falsos (sin Bedrock) y un repo git temporal."""

import shutil
import subprocess
from pathlib import Path

import pytest

from delivery_crew import examples
from delivery_crew.agents import developer
from delivery_crew.agents.developer import DeveloperError, run_developer, seed_run
from delivery_crew.contracts import Change, Design, Requirement
from delivery_crew.runs import NotApprovedError, RunStore

REPO_ROOT = Path(__file__).resolve().parents[1]


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          encoding="utf-8").stdout


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    shutil.copytree(REPO_ROOT / "services" / "auth_service", root / "services" / "auth_service",
                    ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    (root / ".gitignore").write_text("__pycache__/\n.worktrees/\n", encoding="utf-8")
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.name", "Prueba")
    git(root, "config", "user.email", "prueba@example.com")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")
    return root


@pytest.fixture
def store(tmp_path):
    s = RunStore("run-dev", tmp_path / "runs")
    seed_run(s)
    return s


GOOD_RULE = '''from .rules import decline

def frequency_rule_factory(limit=3):
    seen = {}
    def rule(req):
        seen[req.card_token] = seen.get(req.card_token, 0) + 1
        return decline("65") if seen[req.card_token] > limit else None
    return rule
'''
GOOD_TEST = '''from decimal import Decimal
from auth_service.models import AuthorizationRequest
from auth_service.rules import RESPONSE_CODES, authorize
from auth_service.frequency import frequency_rule_factory

def test_fourth_request_is_65():
    RESPONSE_CODES["65"] = "Excede el límite de frecuencia"
    rule = frequency_rule_factory()
    req = AuthorizationRequest("m1", Decimal("10"), "ARS", "tok_demo01")
    codes = [authorize(req, rules=[rule]).response_code for _ in range(4)]
    assert codes == ["00", "00", "00", "65"]
'''


def good_agent(sandbox):
    calls = []

    def run(prompt):
        calls.append(prompt)
        sandbox.read_file("auth_service/rules.py")
        sandbox.write_file("auth_service/frequency.py", GOOD_RULE)
        sandbox.write_file("tests/test_frequency.py", GOOD_TEST)
        return "Agregué la regla de frecuencia (código 65) y su prueba."

    run.calls = calls
    return run


def test_successful_change(repo, store):
    change = run_developer(store, repo, agent_factory=good_agent)

    assert change.test_result == "passed"
    assert change.branch == "feature/usuario-codigo-de-rechazo-65-por-limite-de-frecu"
    assert change.pull_request_url is None
    assert set(change.files_modified) == {
        "services/auth_service/auth_service/frequency.py",
        "services/auth_service/tests/test_frequency.py",
    }
    assert change.approval.status == "pendiente"
    assert "```diff" in change.body and "frequency_rule_factory" in change.body

    # El artefacto quedó escrito y es válido según el contrato.
    assert store.read(Change).test_result == "passed"

    # Commit en la rama del agente, con su autor. El checkout principal no cambió.
    log = git(repo, "log", "feature/usuario-codigo-de-rechazo-65-por-limite-de-frecu", "-1", "--format=%an|%s")
    assert log.startswith("Agente Desarrollador|Código de rechazo 65")
    assert not (repo / "services" / "auth_service" / "auth_service" / "frequency.py").exists()
    assert git(repo, "status", "--porcelain").strip() == ""

    actions = [e["action"] for e in store.read_audit()]
    assert "developer_started" in actions and "tool_write_file" in actions
    assert actions[-1] == "developer_finished"


def test_failing_tests_are_retried_then_reported(repo, store):
    prompts = []

    def factory(sandbox):
        def run(prompt):
            prompts.append(prompt)
            sandbox.write_file("tests/test_roto.py", "def test_roto():\n    assert 1 == 2\n")
            return "intento"
        return run

    change = run_developer(store, repo, agent_factory=factory, max_attempts=3)

    assert len(prompts) == 3
    assert "Las pruebas fallan" in prompts[1] and "test_roto" in prompts[1]
    assert change.test_result == "failed"
    assert change.pull_request_url is None
    # Sin commit: la rama sigue en el commit base.
    assert git(repo, "rev-parse", "feature/usuario-codigo-de-rechazo-65-por-limite-de-frecu") == git(repo, "rev-parse", "main")


def test_fixes_on_second_attempt(repo, store):
    state = {"n": 0}

    def factory(sandbox):
        def run(prompt):
            state["n"] += 1
            body = "assert 1 == 2" if state["n"] == 1 else "assert 2 == 2"
            sandbox.write_file("tests/test_x.py", f"def test_x():\n    {body}\n")
            return f"intento {state['n']}"
        return run

    change = run_developer(store, repo, agent_factory=factory)
    assert change.test_result == "passed" and state["n"] == 2
    assert "Intentos: 2 de 3" in change.body


def test_blocked_when_design_not_approved(repo, tmp_path):
    s = RunStore("sin-aprobar", tmp_path / "runs").create()
    s.write(examples.requirement("sin-aprobar"))
    s.write(examples.design("sin-aprobar", approved=False))
    with pytest.raises(NotApprovedError):
        run_developer(s, repo, agent_factory=good_agent)
    assert not (repo / ".worktrees" / "sin-aprobar").exists()


def test_blocked_when_requirement_not_approved(repo, tmp_path):
    s = RunStore("req-pendiente", tmp_path / "runs").create()
    s.write(examples.requirement("req-pendiente", approved=False))
    s.write(examples.design("req-pendiente"))
    with pytest.raises(NotApprovedError):
        run_developer(s, repo, agent_factory=good_agent)


def test_agent_that_changes_nothing_fails(repo, store):
    with pytest.raises(DeveloperError, match="no modificó"):
        run_developer(store, repo, agent_factory=lambda sb: (lambda prompt: "nada"))
    assert not store.exists(Change)


def test_second_run_requires_fresh(repo, store):
    run_developer(store, repo, agent_factory=good_agent)
    with pytest.raises(DeveloperError, match="--fresh"):
        run_developer(store, repo, agent_factory=good_agent)
    again = run_developer(store, repo, agent_factory=good_agent, fresh=True)
    assert again.test_result == "passed"


def test_prompt_includes_design_and_criteria(store):
    prompt = developer.build_prompt(store.read(Requirement), store.read(Design))
    assert "DynamoDB" in prompt
    assert "La cuarta solicitud en 60 segundos devuelve response_code 65." in prompt
    assert "arquitecto" in prompt
    assert "RECHAZADO" not in prompt


def test_rejection_reason_is_sent_to_the_next_attempt(repo, store):
    run_developer(store, repo, agent_factory=good_agent)
    store.decide(Change, "rechazado", by="tomas", reason="El TTL se renueva en cada solicitud")

    captured = {}

    def factory(sandbox):
        agent = good_agent(sandbox)
        captured["agent"] = agent
        return agent

    again = run_developer(store, repo, agent_factory=factory, fresh=True)
    first_prompt = captured["agent"].calls[0]
    assert "RECHAZADO" in first_prompt
    assert "El TTL se renueva en cada solicitud" in first_prompt
    assert again.approval.status == "pendiente"  # el nuevo cambio vuelve a revisión


def test_approved_previous_change_sends_no_feedback(repo, store):
    run_developer(store, repo, agent_factory=good_agent)
    store.decide(Change, "aprobado", by="tomas")
    captured = {}

    def factory(sandbox):
        captured["agent"] = good_agent(sandbox)
        return captured["agent"]

    run_developer(store, repo, agent_factory=factory, fresh=True)
    assert "RECHAZADO" not in captured["agent"].calls[0]
