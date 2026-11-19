"""Manejador AWS Lambda para POST /authorize (API Gateway, eventos REST v1 o HTTP v2).

Handler de Lambda:  auth_service.handler.lambda_handler
"""

from __future__ import annotations

import base64
import binascii
import json
from typing import Any

from .models import parse_request
from .rules import authorize

MAX_BODY_BYTES = 10_000


def _response(status: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json; charset=utf-8"},
        "body": json.dumps(body, ensure_ascii=False),
    }


def _method(event: dict[str, Any]) -> str:
    http = (event.get("requestContext") or {}).get("http") or {}
    return str(http.get("method") or event.get("httpMethod") or "POST").upper()


def lambda_handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    if _method(event) != "POST":
        return _response(405, {"error": "método no permitido; use POST"})

    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        try:
            raw = base64.b64decode(raw).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            return _response(400, {"error": "cuerpo base64 inválido"})
    if len(raw.encode("utf-8")) > MAX_BODY_BYTES:
        return _response(413, {"error": "cuerpo demasiado grande"})

    try:
        data = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        return _response(400, {"error": "el cuerpo debe ser JSON válido"})

    request, errors = parse_request(data)
    if request is None:
        return _response(400, {"error": "solicitud inválida", "details": errors})

    return _response(200, authorize(request).to_dict())
