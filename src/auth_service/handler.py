"""Synthetic authorization endpoint. It never accepts or stores PAN/CVV data."""

from __future__ import annotations

import json
import os
import time
from typing import Any

import boto3


TABLE_NAME = os.environ["FREQUENCY_TABLE_NAME"]
WINDOW_SECONDS = int(os.environ.get("WINDOW_SECONDS", "60"))
MAX_REQUESTS = int(os.environ.get("MAX_REQUESTS", "3"))
table = boto3.resource("dynamodb").Table(TABLE_NAME)


def response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {"statusCode": status_code, "headers": {"content-type": "application/json"}, "body": json.dumps(body)}


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    try:
        payload = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return response(400, {"message": "El cuerpo debe ser JSON válido."})

    card_token = payload.get("card_token")
    merchant_id = payload.get("merchant_id")
    amount = payload.get("amount")
    if not isinstance(card_token, str) or not card_token or not isinstance(merchant_id, str) or not merchant_id:
        return response(400, {"message": "merchant_id y card_token sintético son obligatorios."})
    if not isinstance(amount, (int, float)) or amount <= 0:
        return response(400, {"message": "amount debe ser un número positivo."})

    now = int(time.time())
    current = table.get_item(Key={"card_token": card_token}).get("Item")
    count = 0 if not current or int(current["expires_at"]) <= now else int(current["request_count"])
    count += 1
    table.put_item(Item={"card_token": card_token, "request_count": count, "expires_at": now + WINDOW_SECONDS})

    if count > MAX_REQUESTS:
        return response(200, {"approved": False, "response_code": "65", "message": "Excede el límite de frecuencia."})
    return response(200, {"approved": True, "response_code": "00", "message": "Autorización sintética aprobada."})
