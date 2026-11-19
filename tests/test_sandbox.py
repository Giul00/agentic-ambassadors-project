import pytest

from delivery_crew.agents.sandbox import MAX_FILE_BYTES, Sandbox, SandboxError


@pytest.fixture
def sandbox(tmp_path):
    svc = tmp_path / "services" / "auth_service"
    (svc / "auth_service").mkdir(parents=True)
    (svc / "tests").mkdir()
    (svc / "auth_service" / "rules.py").write_text("X = 1\n", encoding="utf-8")
    (svc / "tests" / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    (svc / "pytest.ini").write_text("[pytest]\npythonpath = .\ntestpaths = tests\n", encoding="utf-8")
    (tmp_path / "secreto.txt").write_text("no leer", encoding="utf-8")
    events = []
    return Sandbox(tmp_path, on_event=lambda a, d: events.append((a, d))), events


@pytest.mark.parametrize("bad", [
    "../secreto.txt", "../../x.py", "auth_service/../../secreto.txt", "/etc/passwd",
    "C:/Windows/win.ini", "C:secreto.txt", "\\\\server\\share\\x.py", "", "   ",
    ".git/config", "auth_service/__pycache__/x.py", ".env",
])
def test_paths_outside_service_are_rejected(sandbox, bad):
    sb, _ = sandbox
    with pytest.raises(SandboxError):
        sb.resolve(bad)


def test_read_inside_service(sandbox):
    sb, events = sandbox
    assert sb.read_file("auth_service/rules.py") == "X = 1\n"
    assert sb.read_file("auth_service\\rules.py") == "X = 1\n"
    assert events[-1] == ("tool_read_file", {"path": "auth_service/rules.py"})


def test_cannot_read_outside(sandbox):
    sb, _ = sandbox
    with pytest.raises(SandboxError):
        sb.read_file("../../secreto.txt")


def test_write_creates_file_and_reports_event(sandbox):
    sb, events = sandbox
    assert sb.write_file("auth_service/frequency.py", "Y = 2\n") == "auth_service/frequency.py"
    assert (sb.root / "auth_service" / "frequency.py").read_text(encoding="utf-8") == "Y = 2\n"
    assert events[-1] == ("tool_write_file", {"path": "auth_service/frequency.py", "created": True})


def test_write_rejects_disallowed_extension_and_size(sandbox):
    sb, _ = sandbox
    with pytest.raises(SandboxError):
        sb.write_file("run.sh", "rm -rf /")
    with pytest.raises(SandboxError):
        sb.write_file("big.py", "x" * (MAX_FILE_BYTES + 1))


def test_list_files_is_relative_and_hides_caches(sandbox):
    sb, _ = sandbox
    (sb.root / "auth_service" / "__pycache__").mkdir()
    (sb.root / "auth_service" / "__pycache__" / "x.pyc").write_bytes(b"")
    assert sb.list_files() == ["auth_service/rules.py", "pytest.ini", "tests/test_ok.py"]


def test_run_tests_pass_and_fail(sandbox):
    sb, events = sandbox
    ok = sb.run_tests()
    assert ok.passed and "1 passed" in ok.summary
    sb.write_file("tests/test_bad.py", "def test_bad():\n    assert False\n")
    bad = sb.run_tests()
    assert not bad.passed and "failed" in bad.summary
    assert events[-1][0] == "tool_run_tests"


def test_run_tests_has_no_aws_credentials(sandbox, monkeypatch):
    sb, _ = sandbox
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "no-debe-verse")
    sb.write_file("tests/test_env.py", "import os\n\ndef test_env():\n    assert 'AWS_SECRET_ACCESS_KEY' not in os.environ\n")
    assert sb.run_tests().passed


def test_missing_service_dir(tmp_path):
    with pytest.raises(SandboxError):
        Sandbox(tmp_path)


def test_existing_tests_cannot_be_modified_but_new_ones_can(sandbox):
    sb, _ = sandbox
    with pytest.raises(SandboxError, match="prueba existente"):
        sb.write_file("tests/test_ok.py", "def test_ok():\n    pass\n")
    with pytest.raises(SandboxError, match="prueba existente"):
        sb.write_file("pytest.ini", "[pytest]\n")
    assert sb.write_file("tests/test_nuevo.py", "def test_n():\n    assert True\n") == "tests/test_nuevo.py"
    # Un archivo creado por el agente sí lo puede volver a escribir.
    sb.write_file("tests/test_nuevo.py", "def test_n():\n    assert 1\n")
    assert (sb.root / "tests" / "test_ok.py").read_text(encoding="utf-8") == "def test_ok():\n    assert True\n"


def test_protection_can_be_disabled(tmp_path):
    svc = tmp_path / "services" / "auth_service" / "tests"
    svc.mkdir(parents=True)
    (svc / "test_a.py").write_text("x = 1\n", encoding="utf-8")
    sb = Sandbox(tmp_path, protect_existing_tests=False)
    assert sb.write_file("tests/test_a.py", "x = 2\n") == "tests/test_a.py"
