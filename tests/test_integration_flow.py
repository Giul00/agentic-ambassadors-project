"""Integración entre agentes: Desarrollo -> Despliegue, y coherencia entre código, plantilla y health check.

Estas pruebas cubren las uniones que las pruebas de cada agente por separado no ven.
"""

import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest
import yaml

from delivery_crew import examples
from delivery_crew.agents.deployment import create_plan, parameter_overrides
from delivery_crew.agents.developer import run_developer, seed_run
from delivery_crew.contracts import Change, DeployableArtifact, DeploymentComponent, Design
from delivery_crew.conventions import LAMBDA_ENTRYPOINT, SERVICE_DIR, available_services, build_command, lambda_entrypoint, service_dir
from delivery_crew.runs import RunStore

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "sysops" / "cloudformation" / "lambda-dynamodb.yml"
HEALTH_CHECK = ROOT / "templates" / "sysops" / "health-check-authorize.sh"
PIPELINE = ROOT / "templates" / "sysops" / "gitlab-ci-cloudformation.yml"


class _CfnLoader(yaml.SafeLoader):
    """Lee plantillas de CloudFormation ignorando las etiquetas intrínsecas (!Ref, !Sub...)."""


_CfnLoader.add_multi_constructor("!", lambda loader, suffix, node: (
    loader.construct_scalar(node) if isinstance(node, yaml.ScalarNode)
    else loader.construct_sequence(node) if isinstance(node, yaml.SequenceNode)
    else loader.construct_mapping(node)
))


def load_template():
    return yaml.load(TEMPLATE.read_text(encoding="utf-8"), Loader=_CfnLoader)


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, encoding="utf-8").stdout


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    shutil.copytree(ROOT / SERVICE_DIR, root / SERVICE_DIR, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    (root / ".gitignore").write_text("__pycache__/\n.worktrees/\n", encoding="utf-8")
    git(root, "init", "-q", "-b", "main")
    git(root, "-c", "user.name=t", "-c", "user.email=t@t", "add", "-A")
    git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "base")
    return root


def writing_agent(sandbox):
    def run(prompt):
        run.prompt = prompt
        sandbox.write_file("tests/test_marca.py", "def test_marca():\n    assert True\n")
        return "cambio de prueba"
    return run


# --- Desarrollo -> Despliegue ------------------------------------------------

def test_developer_output_is_accepted_by_deployment_agent(repo, tmp_path):
    runs = tmp_path / "runs"
    store = RunStore("e2e", runs)
    seed_run(store)
    captured = {}

    def factory(sandbox):
        captured["agent"] = writing_agent(sandbox)
        return captured["agent"]

    change = run_developer(store, repo, agent_factory=factory)

    # El agente Desarrollador declara el entregable a partir del deployment_spec.
    assert [d.model_dump() for d in change.deliverables] == [{
        "component": "auth-handler", "kind": "zip", "source_path": SERVICE_DIR,
        "build_command": build_command("auth-service"), "entrypoint": LAMBDA_ENTRYPOINT,
    }]
    # Y recibió la configuración de Arquitectura como requisito.
    prompt = captured["agent"].prompt
    assert "Especificación de despliegue" in prompt
    assert "'pk'" in prompt and "'ttl'" in prompt and "STORAGE_BACKEND=dynamodb" in prompt
    assert "TABLE_NAME" in prompt

    store.decide(Change, "aprobado", by="tomas")
    deployment = create_plan("e2e", "123456789012", base_dir=str(runs))

    assert deployment.approval.status == "pendiente"
    manifest = yaml.safe_load((store.path / "generated" / "manifest.yml").read_text(encoding="utf-8"))
    assert manifest["parameter_overrides"] == {
        "TablePartitionKey": "pk",
        "TableTtlAttribute": "ttl",
        "StorageBackend": "dynamodb",
        "LambdaHandler": LAMBDA_ENTRYPOINT,
    }
    pipeline = (store.path / "generated" / ".gitlab-ci-sysops.yml").read_text(encoding="utf-8")
    assert ('CF_EXTRA_PARAMETER_OVERRIDES: "LambdaHandler=auth_service.handler.lambda_handler '
            'StorageBackend=dynamodb TablePartitionKey=pk TableTtlAttribute=ttl"') in pipeline
    assert "SERVICE_DIR: services/auth_service" in pipeline and "SERVICE_PACKAGE: auth_service" in pipeline
    assert "TablePartitionKey=pk" in deployment.body
    assert deployment.stack_name == "dc-auth-service-qa" and deployment.project_name == "dc-auth-service"


# --- Arquitecto -> Desarrollo -> Despliegue ------------------------------------

def test_full_chain_carries_architect_names_to_code_prompt_and_template(repo, tmp_path):
    from delivery_crew.agents.architect import DesignProposal, generate_design

    runs = tmp_path / "runs"
    store = RunStore("cadena", runs).create()
    store.write(examples.requirement("cadena"), actor="orquestador")

    # Nombres distintos de los valores por defecto, para probar que viajan de verdad.
    spec = examples.design().deployment_spec.model_dump()
    for c in spec["components"]:
        if c["kind"] == "dynamodb":
            c["configuration"] = {"partition_key": "token_window", "ttl_attribute": "expira"}
    proposal = DesignProposal(
        summary="Contador por card_token en DynamoDB con ventana fija.",
        components=["auth-service", "DynamoDB"],
        decision="Ventana fija por minuto con clave token_window.",
        verdict="aprobado",
        standards_cited=["ARQ-03", "ARQ-04"],
        deployment_spec=spec,
    )
    generate_design("cadena", runs, agent_fn=lambda prompt: proposal)
    store.decide(Design, "aprobado", by="arquitecto")

    captured = {}

    def factory(sandbox):
        captured["agent"] = writing_agent(sandbox)
        return captured["agent"]

    run_developer(store, repo, agent_factory=factory)
    prompt = captured["agent"].prompt
    assert "'token_window'" in prompt and "'expira'" in prompt

    store.decide(Change, "aprobado", by="tomas")
    create_plan("cadena", "123456789012", base_dir=str(runs))
    manifest = yaml.safe_load((store.path / "generated" / "manifest.yml").read_text(encoding="utf-8"))
    assert manifest["parameter_overrides"]["TablePartitionKey"] == "token_window"
    assert manifest["parameter_overrides"]["TableTtlAttribute"] == "expira"

    actors = [e["actor"] for e in store.read_audit() if e["action"] == "artifact_written"]
    assert actors[:4] == ["orquestador", "agente-arquitecto", "arquitecto", "agente-desarrollador"]


# --- Coherencia de la plantilla ----------------------------------------------

def test_every_override_is_a_template_parameter():
    params = load_template()["Parameters"]
    design = examples.design()
    change = examples.change()
    for name in parameter_overrides(design, change):
        assert name in params, f"la plantilla no tiene el parámetro {name}"


def test_template_defaults_match_the_agreed_convention():
    params = load_template()["Parameters"]
    assert params["TablePartitionKey"]["Default"] == "pk"
    assert params["TableTtlAttribute"]["Default"] == ""  # sin TTL salvo que el diseño lo pida
    assert params["StorageBackend"]["Default"] == "dynamodb"
    assert "Default" not in params["LambdaHandler"]  # siempre viene del entregable


def test_template_wires_parameters_into_resources():
    resources = load_template()["Resources"]
    table = resources["Table"]["Properties"]
    assert table["KeySchema"][0]["AttributeName"] == "TablePartitionKey"
    assert table["AttributeDefinitions"][0]["AttributeName"] == "TablePartitionKey"
    assert "TableTtlAttribute" in str(table["TimeToLiveSpecification"])  # condicional (HasTtl)
    env = resources["Function"]["Properties"]["Environment"]["Variables"]
    assert env["STORAGE_BACKEND"] == "StorageBackend"
    assert env["TABLE_NAME"] == "Table"
    assert resources["ProxyResource"]["Properties"]["PathPart"] == "{proxy+}"
    assert "Tags" not in resources["Api"]["Properties"]  # el rol del workshop no puede etiquetar API Gateway
    assert resources["Function"]["Properties"]["Handler"] == "LambdaHandler"


def test_lambda_role_allows_update_item():
    statements = load_template()["Resources"]["FunctionRole"]["Properties"]["Policies"][0]["PolicyDocument"]["Statement"]
    actions = {a for s in statements for a in s["Action"]}
    assert {"dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem",
            "dynamodb:Scan"} <= actions
    assert all("*" not in a for a in actions)


@pytest.mark.parametrize("service", ["auth-service", "merchants-api"])
def test_handler_entrypoint_exists_in_service(service):
    module, func = lambda_entrypoint(service).rsplit(".", 1)
    path = ROOT / service_dir(service) / (module.replace(".", "/") + ".py")
    assert path.is_file()
    assert f"def {func}(" in path.read_text(encoding="utf-8")


def test_available_services():
    assert {"auth-service", "merchants-api"} <= set(available_services(ROOT))


def test_pipeline_packages_the_real_service():
    text = PIPELINE.read_text(encoding="utf-8")
    assert 'cd "$SERVICE_DIR"' in text and "src/auth_service" not in text
    assert text.count("$CF_EXTRA_PARAMETER_OVERRIDES") == 3


# --- Health check -------------------------------------------------------------

def test_health_check_token_is_accepted_by_the_service():
    from auth_service.models import PAN_LIKE, TOKEN_PATTERN

    script = HEALTH_CHECK.read_text(encoding="utf-8")
    match = re.search(r'token="(tok_[^"$]*)\$\(date \+%s\)_\$\$_\$1"', script)
    assert match, "el script debe generar tokens tok_..._<epoch>_<pid>_<intento>"
    token = f"{match.group(1)}{int(time.time())}_{99999}_b"
    assert TOKEN_PATTERN.fullmatch(token)
    assert not PAN_LIKE.search(token)


def test_health_check_script_uses_lf_line_endings():
    assert b"\r\n" not in HEALTH_CHECK.read_bytes()


# --- Rechazos del agente Despliegue ------------------------------------------

def test_deployment_rejects_configuration_without_template_parameter():
    design = examples.design()
    design.deployment_spec.components.append(
        DeploymentComponent(name="auth-api-2", kind="api_gateway", configuration={"stage": "v2"}))
    with pytest.raises(ValueError, match="no soporta la configuración de auth-api-2"):
        parameter_overrides(design, examples.change())


def test_deployment_rejects_conflicting_values():
    design = examples.design()
    design.deployment_spec.components.append(
        DeploymentComponent(name="otra-tabla", kind="dynamodb", configuration={"partition_key": "id"}))
    with pytest.raises(ValueError, match="valores en conflicto para TablePartitionKey"):
        parameter_overrides(design, examples.change())


def test_deployment_rejects_missing_source_path():
    change = examples.change()
    change.deliverables = [DeployableArtifact(component="auth-handler", kind="zip", source_path="src/auth_service",
                                              build_command="x", entrypoint=LAMBDA_ENTRYPOINT)]
    with pytest.raises(ValueError, match="ruta inexistente: src/auth_service"):
        parameter_overrides(examples.design(), change)


def test_deployment_rejects_source_path_outside_repo():
    change = examples.change()
    change.deliverables = [DeployableArtifact(component="auth-handler", kind="zip", source_path="../..",
                                              build_command="x", entrypoint=LAMBDA_ENTRYPOINT)]
    with pytest.raises(ValueError, match="ruta inexistente"):
        parameter_overrides(examples.design(), change)


def test_design_without_spec_gives_no_deliverables():
    from delivery_crew.agents.developer import build_deliverables

    design = examples.design()
    design.deployment_spec = None
    assert build_deliverables(design) == []
