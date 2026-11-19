"""Lanzar ejecuciones desde el panel: la API arranca el orquestador en segundo plano."""

import threading
import time

import pytest
from fastapi.testclient import TestClient

from delivery_crew import examples, orchestrator as orch
from delivery_crew.agents.narration import Narrator
from delivery_crew.api.app import create_app

NEW_RUN = {
    "title": "Código de rechazo 65",
    "description": "Rechazar con 65 si un card_token supera 3 solicitudes en 60 segundos.",
    "acceptance_criteria": ["La cuarta solicitud devuelve 65.", "  ", "Las tres primeras no cambian."],
    "requested_by": "tomas",
}


class Agents:
    """Agentes falsos; el Arquitecto puede quedar bloqueado hasta que la prueba lo libere."""

    def __init__(self):
        self.calls = []
        self.release_architect = threading.Event()
        self.release_architect.set()

    def factory(self):
        def architect(store):
            self.calls.append(2)
            store.audit("agente-arquitecto", "agent_message", text="Evaluando ARQ-01.")
            self.release_architect.wait(5)
            store.write(examples.design(store.run_id, approved=False), actor="agente-arquitecto")

        def developer(store):
            self.calls.append(3)
            store.write(examples.change(store.run_id, approved=False), actor="agente-desarrollador")

        def deployment(store):
            self.calls.append(4)
            store.write(examples.deployment(store.run_id, approved=False), actor="agente-despliegue")

        return orch.Agents(architect, developer, deployment)


@pytest.fixture
def env(tmp_path):
    agents = Agents()
    app = create_app(tmp_path, agents_factory=agents.factory, target_account="123456789012")
    app.state.runners.poll_seconds = 0.02
    return TestClient(app), agents, app.state.runners


def wait_for(client, run_id, predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        detail = client.get(f"/api/runs/{run_id}").json()
        if predicate(detail):
            return detail
        time.sleep(0.02)
    raise AssertionError(f"no se cumplió la condición; último estado: {detail['state']} {detail['runner']}")


def states(detail):
    return [s["state"] for s in detail["stages"]]


def test_config_exposes_target_account_and_model(env):
    client, _, _ = env
    cfg = client.get("/api/config").json()
    assert cfg["target_account"] == "123456789012" and cfg["model_id"]


def test_create_run_starts_the_flow_and_waits_for_panel_approvals(env):
    client, agents, runners = env
    r = client.post("/api/runs", json=NEW_RUN)
    assert r.status_code == 201
    body = r.json()
    run_id = body["run_id"]
    assert run_id.startswith("codigo-de-rechazo-65-")
    assert body["stages"][0]["artifact"]["acceptance_criteria"] == ["La cuarta solicitud devuelve 65.",
                                                                      "Las tres primeras no cambian."]
    assert body["stages"][0]["artifact"]["approval"]["by"] == "tomas"

    d = wait_for(client, run_id, lambda d: d["stages"][1]["state"] == "por_aprobar")
    assert d["runner"]["active"] is True

    for step in (2, 3, 4):
        wait_for(client, run_id, lambda d, s=step: d["stages"][s - 1]["state"] == "por_aprobar")
        assert client.post(f"/api/runs/{run_id}/stages/{step}/decision",
                           json={"status": "aprobado", "by": "panel"}).status_code == 200

    done = wait_for(client, run_id, lambda d: d["runner"] and not d["runner"]["active"])
    assert done["state"] == "completo" and done["runner"]["outcome"] == orch.COMPLETED
    assert agents.calls == [2, 3, 4]
    actions = [e["action"] for e in client.get(f"/api/runs/{run_id}/audit").json()]
    assert "agent_message" in actions and actions[-1] == "flow_completed"


def test_stage_shows_en_curso_while_the_agent_works(env):
    client, agents, _ = env
    agents.release_architect.clear()
    run_id = client.post("/api/runs", json=NEW_RUN).json()["run_id"]
    d = wait_for(client, run_id, lambda d: any(e["action"] == "agent_message"
                                               for e in client.get(f"/api/runs/{run_id}/audit").json()))
    assert states(d)[1] == "en_curso" and d["runner"]["active"]
    agents.release_architect.set()
    wait_for(client, run_id, lambda d: d["stages"][1]["state"] == "por_aprobar")


def test_cannot_resume_while_running(env):
    client, agents, _ = env
    agents.release_architect.clear()
    run_id = client.post("/api/runs", json=NEW_RUN).json()["run_id"]
    assert client.post(f"/api/runs/{run_id}/resume", json={}).status_code == 409
    agents.release_architect.set()


def test_rejected_change_can_be_retried_from_the_panel(env):
    client, agents, runners = env
    run_id = client.post("/api/runs", json=NEW_RUN).json()["run_id"]
    wait_for(client, run_id, lambda d: d["stages"][1]["state"] == "por_aprobar")
    client.post(f"/api/runs/{run_id}/stages/2/decision", json={"status": "aprobado", "by": "a"})
    wait_for(client, run_id, lambda d: d["stages"][2]["state"] == "por_aprobar")
    client.post(f"/api/runs/{run_id}/stages/3/decision",
                json={"status": "rechazado", "by": "tomas", "reason": "renueva el TTL"})
    stopped = wait_for(client, run_id, lambda d: d["runner"] and not d["runner"]["active"])
    assert (stopped["runner"]["outcome"], stopped["runner"]["step"]) == (orch.REJECTED, 3)

    r = client.post(f"/api/runs/{run_id}/resume", json={"retry_rejected": True})
    assert r.status_code == 200
    wait_for(client, run_id, lambda d: d["stages"][2]["state"] == "por_aprobar")
    assert agents.calls == [2, 3, 3]


def test_resume_complete_run_is_409(env, tmp_path):
    client, _, _ = env
    from delivery_crew.api.samples import create_samples

    create_samples(tmp_path)
    assert client.post("/api/runs/demo-completo/resume", json={}).status_code == 409


def test_resume_unknown_run_is_404(env):
    client, _, _ = env
    assert client.post("/api/runs/no-existe/resume", json={}).status_code == 404


@pytest.mark.parametrize("change", [
    {"title": "x"},
    {"description": "corta"},
    {"acceptance_criteria": []},
    {"acceptance_criteria": ["   "]},
    {"acceptance_criteria": ["x" * 301]},
    {"requested_by": ""},
    {"affected_service": "../etc"},
])
def test_create_run_validates_input(env, change):
    client, agents, _ = env
    assert client.post("/api/runs", json={**NEW_RUN, **change}).status_code == 422
    assert agents.calls == []


def test_agent_failure_is_reported_by_the_runner(tmp_path):
    def factory():
        def boom(store):
            raise RuntimeError("ExpiredToken")
        return orch.Agents(boom, boom, boom)

    app = create_app(tmp_path, agents_factory=factory)
    client = TestClient(app)
    run_id = client.post("/api/runs", json=NEW_RUN).json()["run_id"]
    d = wait_for(client, run_id, lambda d: d["runner"] and not d["runner"]["active"])
    assert d["runner"]["outcome"] == orch.FAILED and "ExpiredToken" in d["runner"]["reason"]


def test_runs_without_runner_report_null(env, tmp_path):
    client, _, _ = env
    from delivery_crew.api.samples import create_samples

    create_samples(tmp_path)
    assert client.get("/api/runs/demo-completo").json()["runner"] is None


# --- narrador -----------------------------------------------------------------

def test_narrator_joins_chunks_and_flushes_on_tool_use_and_complete():
    out = []
    n = Narrator(out.append)
    n(data="Analizo ")
    n(data="ARQ-01.")
    n(event={"contentBlockStart": {"start": {"toolUse": {"name": "read_file"}}}})
    n(data="Listo")
    n(data=".", complete=True)
    n(complete=True)  # sin texto pendiente: no emite
    assert out == ["Analizo ARQ-01.", "Listo."]


def test_narrator_truncates_long_messages():
    out = []
    n = Narrator(out.append, max_chars=10)
    n(data="x" * 50)
    n.flush()
    assert out == ["x" * 10 + " …"]
