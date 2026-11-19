import pytest
from fastapi.testclient import TestClient

from delivery_crew.api.app import create_app
from delivery_crew.api.samples import create_samples


@pytest.fixture
def client(tmp_path):
    create_samples(tmp_path)
    return TestClient(create_app(tmp_path))


def states(detail):
    return [s["state"] for s in detail["stages"]]


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_list_runs_has_summary_states(client):
    runs = {r["run_id"]: r for r in client.get("/api/runs").json()}
    assert set(runs) == {"demo-completo", "demo-por-aprobar", "demo-rechazado", "demo-recien-creado"}
    assert runs["demo-completo"]["state"] == "completo"
    assert runs["demo-por-aprobar"]["state"] == "esperando_aprobacion"
    assert runs["demo-rechazado"]["state"] == "rechazado"


def test_stage_states_per_sample(client):
    get = lambda rid: client.get(f"/api/runs/{rid}").json()
    assert states(get("demo-completo")) == ["aprobado"] * 4
    assert states(get("demo-por-aprobar")) == ["aprobado", "por_aprobar", "esperando", "esperando"]
    assert states(get("demo-rechazado")) == ["aprobado", "rechazado", "esperando", "esperando"]
    assert states(get("demo-recien-creado")) == ["por_aprobar", "esperando", "esperando", "esperando"]


def test_detail_has_artifact_and_labels(client):
    detail = client.get("/api/runs/demo-completo").json()
    design = detail["stages"][1]
    assert design["label"] == "Diseño" and design["filename"] == "02-diseno.md"
    assert design["artifact"]["verdict"] == "aprobado"
    assert detail["stages"][3]["artifact"]["target_account_id"] == "123456789012"


def test_metrics_for_complete_run(client):
    m = client.get("/api/runs/demo-completo").json()["metrics"]
    assert m["elapsed_seconds"] == 11 * 60
    assert m["human_approvals"] == 4
    assert m["automated_steps_done"] == 3 and m["automated_steps_total"] == 3


def test_audit_endpoint(client):
    audit = client.get("/api/runs/demo-completo/audit").json()
    assert audit[0]["action"] == "run_created"
    assert audit[-1]["action"] == "approval_aprobado"


def test_approve_unlocks_next_stage(client):
    r = client.post("/api/runs/demo-por-aprobar/stages/2/decision",
                    json={"status": "aprobado", "by": "arquitecto"})
    assert r.status_code == 200
    assert states(r.json()) == ["aprobado", "aprobado", "en_curso", "esperando"]
    audit = client.get("/api/runs/demo-por-aprobar/audit").json()
    assert audit[-1]["action"] == "approval_aprobado" and audit[-1]["actor"] == "arquitecto"


def test_reject_requires_reason(client):
    r = client.post("/api/runs/demo-por-aprobar/stages/2/decision",
                    json={"status": "rechazado", "by": "arquitecto"})
    assert r.status_code == 422


def test_reject_with_reason_stops_flow(client):
    r = client.post("/api/runs/demo-por-aprobar/stages/2/decision",
                    json={"status": "rechazado", "by": "arquitecto", "reason": "falta un estándar"})
    assert r.status_code == 200
    assert r.json()["state"] == "rechazado"
    assert r.json()["stages"][1]["artifact"]["approval"]["reason"] == "falta un estándar"


def test_cannot_decide_a_stage_that_is_not_pending(client):
    for rid, step in [("demo-completo", 2), ("demo-por-aprobar", 3), ("demo-rechazado", 2)]:
        r = client.post(f"/api/runs/{rid}/stages/{step}/decision",
                        json={"status": "aprobado", "by": "x"})
        assert r.status_code == 409, (rid, step)


def test_cannot_decide_twice(client):
    body = {"status": "aprobado", "by": "arquitecto"}
    assert client.post("/api/runs/demo-por-aprobar/stages/2/decision", json=body).status_code == 200
    assert client.post("/api/runs/demo-por-aprobar/stages/2/decision", json=body).status_code == 409


def test_decision_requires_author_and_valid_status(client):
    url = "/api/runs/demo-por-aprobar/stages/2/decision"
    assert client.post(url, json={"status": "aprobado", "by": ""}).status_code == 422
    assert client.post(url, json={"status": "quizas", "by": "x"}).status_code == 422
    assert client.post(url, json={"status": "aprobado"}).status_code == 422


def test_unknown_step(client):
    r = client.post("/api/runs/demo-por-aprobar/stages/9/decision", json={"status": "aprobado", "by": "x"})
    assert r.status_code == 409


def test_unknown_run_is_404(client):
    assert client.get("/api/runs/no-existe").status_code == 404
    assert client.get("/api/runs/no-existe/audit").status_code == 404


@pytest.mark.parametrize("bad", ["..", ".oculto", "a%2Fb", "x" * 100])
def test_invalid_run_id_never_reads_outside(client, bad):
    assert client.get(f"/api/runs/{bad}").status_code in (400, 404)


def test_corrupt_artifact_is_reported_not_crashing(client, tmp_path):
    (tmp_path / "demo-por-aprobar" / "02-diseno.md").write_text("basura", encoding="utf-8")
    detail = client.get("/api/runs/demo-por-aprobar").json()
    assert detail["stages"][1]["state"] == "invalido"
    assert "02-diseno.md" in detail["stages"][1]["error"]
    assert detail["state"] == "invalido"


def test_cors_allows_vite_origin_only(client):
    ok = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    other = client.get("/api/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in other.headers


def test_empty_runs_dir(tmp_path):
    c = TestClient(create_app(tmp_path / "vacio"))
    assert c.get("/api/runs").json() == []
