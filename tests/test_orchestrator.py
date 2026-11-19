import threading

import pytest

from delivery_crew import examples, orchestrator as orch
from delivery_crew.contracts import Change, Deployment, Design, Requirement
from delivery_crew.runs import RunStore


class FakeAgents:
    """Agentes falsos que escriben artefactos de ejemplo pendientes de aprobación."""

    def __init__(self, design=None, change=None, fail_on=None):
        self.calls: list[int] = []
        self.design = design or (lambda rid: examples.design(rid, approved=False))
        self.change = change or (lambda rid: examples.change(rid, approved=False))
        self.fail_on = fail_on

    def _run(self, step, store, artifact):
        self.calls.append(step)
        if self.fail_on == step:
            raise RuntimeError("Bedrock no responde")
        store.write(artifact, actor=f"agente-{step}")

    def agents(self):
        return orch.Agents(
            architect=lambda s: self._run(2, s, self.design(s.run_id)),
            developer=lambda s: self._run(3, s, self.change(s.run_id)),
            deployment=lambda s: self._run(4, s, examples.deployment(s.run_id, approved=False)),
        )


def approve_all(by="persona"):
    def decide(store, step):
        store.decide(orch.ARTIFACTS[step - 1], "aprobado", by=by)
    return decide


@pytest.fixture
def store(tmp_path):
    s = RunStore("orq-1", tmp_path)
    orch.start(s, examples.requirement("orq-1", approved=False), requested_by="tomas")
    return s


def quiet(_msg):
    pass


def test_start_creates_requirement_approved_by_requester(store):
    req = store.read(Requirement)
    assert req.approval.status == "aprobado" and req.approval.by == "tomas"


def test_start_twice_is_rejected(store):
    with pytest.raises(FileExistsError):
        orch.start(store, examples.requirement("orq-1"), requested_by="tomas")


def test_happy_path_runs_agents_in_order(store):
    fake = FakeAgents()
    result = orch.run(store, fake.agents(), decide=approve_all(), log=quiet)
    assert result.outcome == orch.COMPLETED
    assert fake.calls == [2, 3, 4]
    actions = [e["action"] for e in store.read_audit() if e["actor"] == "orquestador"]
    assert actions.count("stage_started") == 3 and actions.count("stage_finished") == 3
    assert actions[-1] == "flow_completed"


def test_waits_for_approval_without_rerunning_agents(store):
    fake = FakeAgents()
    first = orch.run(store, fake.agents(), wait=False, log=quiet)
    assert (first.outcome, first.step) == (orch.WAITING, 2)
    again = orch.run(store, fake.agents(), wait=False, log=quiet)
    assert (again.outcome, again.step) == (orch.WAITING, 2)
    assert fake.calls == [2]  # idempotente: no vuelve a correr el Arquitecto

    store.decide(Design, "aprobado", by="arquitecto")  # como haría el panel
    nxt = orch.run(store, fake.agents(), wait=False, log=quiet)
    assert (nxt.outcome, nxt.step) == (orch.WAITING, 3)
    assert fake.calls == [2, 3]


def test_waiting_is_audited_once_per_stage(store):
    """Mientras espera, relee varias veces pero audita la espera una sola vez (sin depender del reloj)."""

    class Stop(Exception):
        pass

    sleeps = []

    def fake_sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) >= 3:
            raise Stop

    with pytest.raises(Stop):
        orch.run(store, FakeAgents().agents(), wait=True, poll_seconds=0.5, log=quiet, sleep=fake_sleep)
    waits = [e for e in store.read_audit() if e["action"] == "waiting_approval"]
    assert len(waits) == 1 and waits[0]["step"] == 2
    assert sleeps == [0.5, 0.5, 0.5]


def test_wait_timeout_returns_waiting(store):
    result = orch.run(store, FakeAgents().agents(), wait=True, poll_seconds=0, timeout_seconds=0, log=quiet,
                      sleep=lambda s: None)
    assert (result.outcome, result.step) == (orch.WAITING, 2)


def test_approval_from_panel_while_waiting(store):
    """Otro proceso (el panel) aprueba mientras el orquestador espera."""
    fake = FakeAgents()
    stop = threading.Event()

    def panel():
        while not stop.is_set():
            for cls in (Design, Change, Deployment):
                try:
                    if store.exists(cls) and store.read(cls).approval.status == "pendiente":
                        store.decide(cls, "aprobado", by="panel")
                except Exception:
                    pass
            stop.wait(0.01)

    t = threading.Thread(target=panel)
    t.start()
    try:
        result = orch.run(store, fake.agents(), poll_seconds=0.01, timeout_seconds=10, log=quiet)
    finally:
        stop.set()
        t.join()
    assert result.outcome == orch.COMPLETED
    assert store.read(Deployment).approval.by == "panel"


def test_rejected_design_stops_the_flow(store):
    fake = FakeAgents()

    def decide(s, step):
        s.decide(Design, "rechazado", by="arquitecto", reason="falta el estándar de TTL")

    result = orch.run(store, fake.agents(), decide=decide, log=quiet)
    assert (result.outcome, result.step, result.reason) == (orch.REJECTED, 2, "falta el estándar de TTL")
    assert fake.calls == [2]
    assert store.read_audit()[-1]["action"] == "flow_stopped"


def test_approved_design_with_non_approved_verdict_is_blocked(store):
    def design(rid):
        d = examples.design(rid, approved=False)
        return d.model_copy(update={"verdict": "observaciones", "open_questions": ["¿Qué tabla?"]})

    fake = FakeAgents(design=design)
    result = orch.run(store, fake.agents(), decide=approve_all(), log=quiet)
    assert (result.outcome, result.step) == (orch.BLOCKED, 2)
    assert "observaciones" in result.reason
    assert fake.calls == [2]


def test_approved_change_with_failing_tests_is_blocked(store):
    def change(rid):
        c = examples.change(rid, approved=False)
        return c.model_copy(update={"test_result": "failed", "pull_request_url": None})

    fake = FakeAgents(change=change)
    result = orch.run(store, fake.agents(), decide=approve_all(), log=quiet)
    assert (result.outcome, result.step) == (orch.BLOCKED, 3)
    assert fake.calls == [2, 3]


def test_rejected_change_can_be_retried(store):
    fake = FakeAgents()
    decisions = iter(["aprobado", "rechazado"])

    def decide(s, step):
        status = next(decisions)
        s.decide(orch.ARTIFACTS[step - 1], status, by="tomas", reason="usa memoria" if status == "rechazado" else None)

    first = orch.run(store, fake.agents(), decide=decide, log=quiet)
    assert (first.outcome, first.step) == (orch.REJECTED, 3)

    second = orch.run(store, fake.agents(), decide=approve_all(), retry_rejected=True, log=quiet)
    assert second.outcome == orch.COMPLETED
    assert fake.calls == [2, 3, 3, 4]
    started = [e for e in store.read_audit() if e["action"] == "stage_started" and e["step"] == 3]
    assert started[-1].get("retry") is True


def test_retry_does_not_apply_to_rejected_design(store):
    fake = FakeAgents()
    orch.run(store, fake.agents(),
             decide=lambda s, step: s.decide(Design, "rechazado", by="a", reason="no"), log=quiet)
    result = orch.run(store, fake.agents(), retry_rejected=True, wait=False, log=quiet)
    assert result.outcome == orch.REJECTED and fake.calls == [2]


def test_agent_failure_is_reported_and_audited(store):
    fake = FakeAgents(fail_on=3)
    result = orch.run(store, fake.agents(), decide=approve_all(), log=quiet)
    assert (result.outcome, result.step) == (orch.FAILED, 3)
    assert "Bedrock no responde" in result.reason
    failed = [e for e in store.read_audit() if e["action"] == "stage_failed"]
    assert failed and failed[0]["step"] == 3
    # Se puede reanudar cuando el problema se resuelve.
    fake.fail_on = None
    assert orch.run(store, fake.agents(), decide=approve_all(), log=quiet).outcome == orch.COMPLETED


def test_agent_that_writes_nothing_is_a_failure(store):
    agents = orch.Agents(architect=lambda s: None, developer=lambda s: None, deployment=lambda s: None)
    result = orch.run(store, agents, log=quiet)
    assert (result.outcome, result.step) == (orch.FAILED, 2)


def test_invalid_artifact_stops_the_flow(store):
    (store.path / "02-diseno.md").write_text("basura", encoding="utf-8")
    result = orch.run(store, FakeAgents().agents(), log=quiet)
    assert (result.outcome, result.step) == (orch.INVALID, 2)


def test_run_without_requirement_is_invalid(tmp_path):
    s = RunStore("vacia", tmp_path).create()
    assert orch.run(s, FakeAgents().agents(), log=quiet).outcome == orch.INVALID


def test_terminal_decider_approves_and_rejects(store):
    fake = FakeAgents()
    answers = iter(["x", "a", "r", "", "no cubre el borde de 60 s"])
    out = []
    decide = orch.terminal_decider("tomas", ask=lambda prompt: next(answers), out=out.append)
    result = orch.run(store, fake.agents(), decide=decide, log=quiet)
    assert (result.outcome, result.step) == (orch.REJECTED, 3)
    assert store.read(Design).approval.by == "tomas"
    assert store.read(Change).approval.reason == "no cubre el borde de 60 s"
    assert any("Veredicto: aprobado" in line for line in out)


def test_make_run_id_is_valid_for_runstore():
    rid = orch.make_run_id("Código de rechazo 65 / límite!")
    RunStore(rid, "x")  # no lanza: es un id válido
    assert rid.startswith("codigo-de-rechazo-65-limite-")


def test_cli_start_validates_arguments(tmp_path, capsys):
    assert orch.main(["start", "--runs-dir", str(tmp_path), "--title", "x"]) == 2
    assert orch.main(["start", "--runs-dir", str(tmp_path), "--example", "--target-account", "123"]) == 2
    assert orch.main(["start", "--runs-dir", str(tmp_path), "--example", "--interactive"]) == 2


def test_cli_status(tmp_path, capsys, store):
    assert orch.main(["status", "--run-id", "orq-1", "--runs-dir", str(store.path.parent)]) == 0
    assert "1. Requerimiento" in capsys.readouterr().out
    assert orch.main(["status", "--run-id", "no-existe", "--runs-dir", str(tmp_path)]) == 1
