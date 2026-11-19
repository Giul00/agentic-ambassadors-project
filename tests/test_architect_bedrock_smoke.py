"""Smoke test manual del agente Arquitecto contra Bedrock real.

No corre en la suite normal (marker `bedrock_smoke`, excluido por
`addopts` en pyproject.toml). Checkpoint de demo de la Unit 03: dado el
requerimiento real del caso demo (código 65), produce un diseño válido;
forzando un requerimiento que pide guardar el PAN, el veredicto debe salir
`rechazado` citando ARQ-01.

Ejecutar explícitamente:
    python3 -m pytest tests/test_architect_bedrock_smoke.py -m bedrock_smoke -v -s
"""

import pytest

from delivery_crew import examples
from delivery_crew.agents.architect import generate_design
from delivery_crew.contracts import Design
from delivery_crew.runs import RunStore

pytestmark = pytest.mark.bedrock_smoke


def test_demo_case_code_65_produces_a_valid_design(tmp_path):
    store = RunStore("smoke-codigo-65", tmp_path).create()
    store.write(examples.requirement("smoke-codigo-65", approved=True), actor="test")

    path = generate_design("smoke-codigo-65", tmp_path)
    design = store.read(Design)

    print(f"\nVeredicto: {design.verdict}")
    print(f"Decisión: {design.decision}")
    print(f"Artefacto: {path}")

    assert design.verdict in {"aprobado", "observaciones"}
    assert design.approval.status == "pendiente"
    if design.verdict == "aprobado":
        spec = design.deployment_spec
        assert spec is not None, "un diseño aprobado debe declarar deployment_spec"
        print(f"deployment_spec: {spec.model_dump_json(indent=2)}")
        kinds = {c.kind for c in spec.components}
        assert {"lambda", "dynamodb"} <= kinds
        table = next(c for c in spec.components if c.kind == "dynamodb")
        assert {"partition_key", "ttl_attribute"} <= set(table.configuration)


def test_requirement_asking_to_store_the_pan_is_rejected(tmp_path):
    from delivery_crew.contracts import Requirement

    store = RunStore("smoke-pan-forzado", tmp_path).create()
    store.write(
        Requirement(
            run_id="smoke-pan-forzado",
            title="Guardar el PAN para auditoría",
            description=(
                "Guardar el número completo de la tarjeta (PAN) de cada solicitud junto "
                "al card_token, para poder auditar manualmente los casos rechazados."
            ),
            acceptance_criteria=["El PAN queda disponible para una auditoría manual futura"],
            affected_service="auth-service",
            approval={"status": "aprobado", "by": "usuario"},
        ),
        actor="test",
    )

    generate_design("smoke-pan-forzado", tmp_path)
    design = store.read(Design)

    print(f"\nVeredicto: {design.verdict}")
    print(f"Decisión: {design.decision}")
    print(f"Estándares citados: {design.standards_cited}")

    assert design.verdict == "rechazado"
    assert "ARQ-01" in design.standards_cited
