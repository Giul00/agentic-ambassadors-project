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
        )

    path = generate_design("run-1", store.path.parent, agent_fn=fake_agent)
    assert path.exists()

    design = store.read(Design)
    assert design.verdict == "aprobado"
    assert design.approval.status == "pendiente"  # el agente nunca autoaprueba
    assert "ARQ-03" in design.standards_cited

    content = path.read_text(encoding="utf-8")
    assert "```mermaid" in content


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
