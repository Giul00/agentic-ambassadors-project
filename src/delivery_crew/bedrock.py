"""Acceso a Amazon Bedrock. Modelo y región se leen del entorno, sin valores fijos de cuenta."""

from __future__ import annotations

import os

DEFAULT_REGION = "us-west-2"
DEFAULT_MODEL_ID = "us.anthropic.claude-sonnet-4-6"
FAST_MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"


def region() -> str:
    return os.environ.get("AWS_DEFAULT_REGION") or os.environ.get("AWS_REGION") or DEFAULT_REGION


def model_id(fast: bool = False) -> str:
    """Modelo por defecto, o el rápido y barato. Se puede cambiar con DELIVERY_CREW_MODEL_ID."""
    override = os.environ.get("DELIVERY_CREW_MODEL_ID")
    if override:
        return override
    return FAST_MODEL_ID if fast else DEFAULT_MODEL_ID


def get_strands_model(fast: bool = False, **kwargs):
    """Modelo de Strands Agents para usar al crear un Agent."""
    from strands.models import BedrockModel

    return BedrockModel(model_id=model_id(fast), region_name=region(), **kwargs)


def ask(prompt: str, fast: bool = False, max_tokens: int = 256) -> str:
    """Llamada directa y mínima a Bedrock (Converse). Útil para comprobar el entorno."""
    import boto3

    client = boto3.client("bedrock-runtime", region_name=region())
    response = client.converse(
        modelId=model_id(fast),
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": max_tokens},
    )
    return response["output"]["message"]["content"][0]["text"]
