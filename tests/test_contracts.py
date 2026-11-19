import pytest

from delivery_crew import examples
from delivery_crew.contracts import (
    ARTIFACTS,
    Approval,
    Change,
    ContractError,
    Deployment,
    Design,
    Requirement,
)


@pytest.mark.parametrize("factory", [examples.requirement, examples.design, examples.change, examples.deployment])
def test_roundtrip_markdown(factory):
    original = factory()
    restored = type(original).from_markdown(original.to_markdown())
    assert restored == original


def test_all_artifacts_have_unique_files_and_steps():
    assert len({a.FILENAME for a in ARTIFACTS}) == 4
    assert [a.STEP for a in ARTIFACTS] == [1, 2, 3, 4]


def test_missing_field_is_reported_by_name():
    text = examples.requirement().to_markdown().replace("affected_service: auth-service\n", "")
    with pytest.raises(ContractError) as exc:
        Requirement.from_markdown(text)
    assert "affected_service" in str(exc.value)


def test_missing_front_matter_is_rejected():
    with pytest.raises(ContractError, match="bloque YAML"):
        Requirement.from_markdown("solo texto")


def test_unknown_field_is_rejected():
    text = examples.requirement().to_markdown().replace("---\n\n", "campo_extra: 1\n---\n\n", 1)
    with pytest.raises(ContractError):
        Requirement.from_markdown(text)


def test_requirement_needs_acceptance_criteria():
    with pytest.raises(ValueError) as exc:
        Requirement(**{**examples.requirement().model_dump(), "acceptance_criteria": []})
    assert "acceptance_criteria" in str(exc.value)


def test_unknown_field_error_names_the_field():
    text = examples.requirement().to_markdown().replace("---\n\n", "campo_extra: 1\n---\n\n", 1)
    with pytest.raises(ContractError) as exc:
        Requirement.from_markdown(text)
    assert "campo_extra" in str(exc.value)


def test_approval_requires_author():
    with pytest.raises(ValueError):
        Approval(status="aprobado")


def test_rejection_requires_reason():
    with pytest.raises(ValueError):
        Approval(status="rechazado", by="arquitecto")
    assert Approval(status="rechazado", by="arquitecto", reason="viola un estándar").status == "rechazado"


def test_non_approved_verdict_needs_support():
    with pytest.raises(ValueError):
        Design(**{**examples.design().model_dump(), "verdict": "rechazado",
                  "standards_cited": [], "open_questions": []})


def test_pull_request_not_allowed_with_failing_tests():
    with pytest.raises(ValueError):
        Change(**{**examples.change().model_dump(), "test_result": "failed"})


def test_deployment_account_must_be_12_digits():
    with pytest.raises(ValueError):
        Deployment(**{**examples.deployment().model_dump(), "target_account_id": "abc"})
