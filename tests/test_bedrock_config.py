from delivery_crew import bedrock


def test_default_model(monkeypatch):
    monkeypatch.delenv("DELIVERY_CREW_MODEL_ID", raising=False)
    assert bedrock.model_id() == "us.anthropic.claude-sonnet-4-6"
    assert bedrock.model_id(fast=True) == bedrock.FAST_MODEL_ID


def test_model_override(monkeypatch):
    monkeypatch.setenv("DELIVERY_CREW_MODEL_ID", "us.amazon.nova-pro-v1:0")
    assert bedrock.model_id() == "us.amazon.nova-pro-v1:0"
    assert bedrock.model_id(fast=True) == "us.amazon.nova-pro-v1:0"


def test_region_from_env_or_default(monkeypatch):
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    monkeypatch.delenv("AWS_REGION", raising=False)
    assert bedrock.region() == "us-west-2"
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    assert bedrock.region() == "us-east-1"
