"""Pruebas de la Unit 03: agente Arquitecto.

No llaman a Bedrock: inyectan `agent_fn` para probar la compuerta de
aprobación, la construcción del artefacto y la cita de estándares. El
smoke test real contra Bedrock está en test_architect_bedrock_smoke.py
(marker bedrock_smoke, no corre en la suite normal).
"""

import pytest

from delivery_crew import examples
from delivery_crew.agents.architect import DesignProposal, generate_design, load_standards
from delivery_crew.contracts import Design, Requirement
from delivery_crew.runs import NotApprovedError, RunStore


@pytest.fixture
def store(tmp_path):
    return RunStore("run-1", tmp_path).create()


def test_load_standards_includes_the_seven_ids():
    text = load_standards()
    for i in range(1, 8):
        assert f"ARQ-{i:02d}" in text


def test_blocked_until_requirement_is_approved(store):
    store.write(examples.requirement("run-1", approved=False), actor="test")
    with pytest.raises(NotApprovedError):
        generate_design("run-1", store.path.parent, agent_fn=lambda _p: None)


def test_valid_design_is_written_with_diagram_and_cited_standards(store):
    store.write(examples.requirement("run-1", approved=True), actor="test")

    def fake_agent(_prompt: str) -> DesignProposal:
        return DesignProposal(
            summary="Contador de frecuencia por card_token en DynamoDB con TTL de 60s",
            components=["auth-service", "DynamoDB: tabla de frecuencia"],
            decision=(
                "Usar DynamoDB con TTL de 60s para el contador. Alternativa descartada: "
                "memoria del proceso Lambda, porque no persiste entre invocaciones frías."
            ),
            risks=["Costo extra de la tabla DynamoDB (bajo, demo)"],
            verdict="aprobado",
            standards_cited=["ARQ-03", "ARQ-04"],
            diagram_mermaid="flowchart LR\n  A[auth-service] --> B[(DynamoDB TTL)]",
            deployment_spec=examples.design().deployment_spec,
        )

    path = generate_design("run-1", store.path.parent, agent_fn=fake_agent)
    assert path.exists()

    design = store.read(Design)
    assert design.verdict == "aprobado"
    assert design.approval.status == "pendiente"  # el agente nunca autoaprueba
    assert "ARQ-03" in design.standards_cited

    content = path.read_text(encoding="utf-8")
    assert "```mermaid" in content
    # El deployment_spec llega al artefacto (lo necesitan Desarrollo y SysOps).
    assert design.deployment_spec == examples.design().deployment_spec


def test_forced_violation_is_rejected_citing_the_standard(store):
    """Caso de prueba del Risk de la Unit 03: forzar un incumplimiento (guardar
    el PAN) y verificar que el veredicto lo marca citando ARQ-01."""
    store.write(
        examples.requirement("run-1", approved=True),
        actor="test",
    )

    def fake_agent(_prompt: str) -> DesignProposal:
        return DesignProposal(
            summary="Guardar el PAN junto al card_token para auditoría manual",
            components=["auth-service"],
            decision="Incumple ARQ-01: no se puede almacenar el PAN bajo ninguna forma.",
            risks=["Exposición de datos reales de tarjetas"],
            verdict="rechazado",
            standards_cited=["ARQ-01"],
            diagram_mermaid=None,
        )

    generate_design("run-1", store.path.parent, agent_fn=fake_agent)
    design = store.read(Design)
    assert design.verdict == "rechazado"
    assert "ARQ-01" in design.standards_cited


def test_ambiguous_requirement_leaves_open_questions_instead_of_guessing(store):
    store.write(examples.requirement("run-1", approved=True), actor="test")

    def fake_agent(_prompt: str) -> DesignProposal:
        return DesignProposal(
            summary="El requerimiento no especifica qué comportamiento cambiar ni con qué criterio",
            components=["auth-service"],
            decision="No se puede diseñar sin resolver las preguntas abiertas",
            verdict="observaciones",
            open_questions=[
                "¿Qué comportamiento concreto cambia?",
                "¿Qué criterio de aceptación define 'mejorar'?",
            ],
            diagram_mermaid=None,
        )

    path = generate_design("run-1", store.path.parent, agent_fn=fake_agent)
    design = Design.from_markdown(path.read_text(encoding="utf-8"))
    assert design.verdict == "observaciones"
    assert len(design.open_questions) == 2
    assert design.standards_cited == []


def test_verdict_without_standards_or_questions_is_rejected_by_the_schema():
    with pytest.raises(ValueError):
        DesignProposal(
            summary="x" * 20,
            components=["auth-service"],
            decision="y" * 20,
            verdict="rechazado",
        )


# --- deployment_spec ---------------------------------------------------------

def _approved(**overrides):
    base = dict(
        summary="Contador por card_token en DynamoDB",
        components=["auth-service", "DynamoDB"],
        decision="Ventana fija por minuto en DynamoDB.",
        verdict="aprobado",
        standards_cited=["ARQ-03"],
        deployment_spec=examples.design().deployment_spec.model_dump(),
    )
    base.update(overrides)
    return base


def _spec(**changes):
    spec = examples.design().deployment_spec.model_dump()
    spec.update(changes)
    return spec


def test_approved_design_requires_deployment_spec():
    with pytest.raises(ValueError, match="debe incluir deployment_spec"):
        DesignProposal(**_approved(deployment_spec=None))


def test_non_approved_design_may_omit_deployment_spec():
    p = DesignProposal(**_approved(verdict="observaciones", open_questions=["¿Qué tabla?"], deployment_spec=None))
    assert p.deployment_spec is None


def test_unsupported_component_kind_is_rejected():
    comps = _spec()["components"] + [{"name": "ledger", "kind": "rds", "depends_on": [], "configuration": {}}]
    with pytest.raises(ValueError, match="sin plantilla homologada: rds"):
        DesignProposal(**_approved(deployment_spec=_spec(components=comps)))


def test_dangling_dependency_is_rejected():
    comps = _spec()["components"]
    comps[0]["depends_on"] = ["no-existe"]
    with pytest.raises(ValueError, match="componentes inexistentes: no-existe"):
        DesignProposal(**_approved(deployment_spec=_spec(components=comps)))


def test_null_lists_from_the_model_are_accepted_as_empty():
    p = DesignProposal(**_approved(open_questions=None, risks=None))
    assert p.open_questions == [] and p.risks == []


def test_dependency_cycle_is_rejected():
    """Caso visto con Bedrock real: la lambda dependía de la API y la API de la lambda."""
    comps = _spec()["components"]
    for c in comps:
        if c["kind"] == "lambda":
            c["depends_on"] = ["frequency-store", "auth-api"]
    with pytest.raises(ValueError, match="ciclo: auth-api -> auth-handler -> auth-api"):
        DesignProposal(**_approved(deployment_spec=_spec(components=comps)))


def test_find_cycle_examples():
    from delivery_crew.agents.architect import _find_cycle

    assert _find_cycle({"a": ["b"], "b": ["c"], "c": []}) is None
    assert _find_cycle({"a": ["a"]}) == ["a", "a"]
    assert _find_cycle({"a": ["b"], "b": ["c"], "c": ["a"]}) == ["a", "b", "c", "a"]
    assert _find_cycle({"x": [], "a": ["b"], "b": ["x", "a"]}) == ["a", "b", "a"]


def test_duplicate_component_names_are_rejected():
    comps = _spec()["components"]
    comps.append(dict(comps[0]))
    with pytest.raises(ValueError, match="repetidos"):
        DesignProposal(**_approved(deployment_spec=_spec(components=comps)))


def test_dynamodb_must_declare_key_names():
    comps = _spec()["components"]
    for c in comps:
        if c["kind"] == "dynamodb":
            c["configuration"] = {"partition_key": "pk"}
    with pytest.raises(ValueError, match="debe declarar en configuration: ttl_attribute"):
        DesignProposal(**_approved(deployment_spec=_spec(components=comps)))


def test_unknown_standard_id_is_rejected():
    with pytest.raises(ValueError, match="no existen: ARQ-99"):
        DesignProposal(**_approved(standards_cited=["ARQ-03", "ARQ-99"]))


def test_prompt_lists_supported_kinds_and_configuration_keys():
    from delivery_crew.agents.architect import SYSTEM_PROMPT_TEMPLATE, deployment_rules

    rules = deployment_rules()
    for kind in ("api_gateway", "lambda", "dynamodb"):
        assert kind in rules
    for kind, key in (("dynamodb", "partition_key"), ("dynamodb", "ttl_attribute"), ("lambda", "FREQUENCY_STORE")):
        assert f"en componentes `{kind}`, clave `{key}` (sin prefijo)" in rules
    assert "ecs" not in rules.split("homologada:")[1].split(".")[0]  # perfil pendiente, no se ofrece
    rendered = SYSTEM_PROMPT_TEMPLATE.format(standards="S", deployment_rules=rules)
    assert "deployment_spec" in rendered
