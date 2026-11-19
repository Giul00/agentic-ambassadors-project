import pytest

from delivery_crew import examples
from delivery_crew.contracts import ContractError, Design
from delivery_crew.runs import NotApprovedError, RunStore


@pytest.fixture
def store(tmp_path):
    return RunStore("run-1", tmp_path).create()


def test_write_and_read(store):
    store.write(examples.requirement("run-1"), actor="test")
    assert store.read(type(examples.requirement())).title.startswith("Código")


def test_artifact_from_other_run_is_rejected(store):
    with pytest.raises(ContractError):
        store.write(examples.requirement("otra-ejecucion"))


@pytest.mark.parametrize("bad", ["../fuera", "a/b", "", "..", ".oculto", "x" * 100])
def test_run_id_cannot_escape_runs_dir(tmp_path, bad):
    with pytest.raises(ValueError):
        RunStore(bad, tmp_path)


def test_next_step_blocked_until_approved(store):
    store.write(examples.requirement("run-1", approved=False), actor="test")
    with pytest.raises(NotApprovedError):
        store.read_input_for(2, type(examples.requirement()))


def test_next_step_allowed_after_approval(store):
    req = type(examples.requirement())
    store.write(examples.requirement("run-1", approved=False), actor="test")
    store.decide(req, "aprobado", by="tomas")
    assert store.read_input_for(2, req).approval.status == "aprobado"


def test_rejected_artifact_blocks_next_step(store):
    req = type(examples.requirement())
    store.write(examples.requirement("run-1", approved=False), actor="test")
    store.decide(req, "rechazado", by="tomas", reason="falta contexto")
    with pytest.raises(NotApprovedError):
        store.read_input_for(2, req)


def test_step_one_has_no_previous(store):
    with pytest.raises(ValueError):
        store.read_input_for(1, type(examples.requirement()))


def test_audit_records_writes_and_decisions(store):
    req = type(examples.requirement())
    store.write(examples.requirement("run-1", approved=False), actor="agente")
    store.decide(req, "aprobado", by="tomas")
    actions = [e["action"] for e in store.read_audit()]
    assert actions == ["run_created", "artifact_written", "artifact_written", "approval_aprobado"]
    assert all(e["run_id"] == "run-1" and "at" in e and "actor" in e for e in store.read_audit())


def test_missing_artifact(store):
    with pytest.raises(FileNotFoundError):
        store.read(Design)


def test_demo_run_is_valid(tmp_path):
    demo = examples.write_demo_run(tmp_path)
    for step in (2, 3, 4):
        from delivery_crew.contracts import BY_STEP
        assert demo.read_input_for(step, BY_STEP[step]).run_id == examples.DEMO_RUN_ID
