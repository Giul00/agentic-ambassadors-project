"""Modelo de la solicitud de autorización y validación de entrada.

Datos 100 % sintéticos: card_token es un identificador inventado con el formato tok_xxxx.
Cualquier valor que parezca un número de tarjeta (PAN) se rechaza.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

# Monto máximo por operación, por moneda.
MAX_AMOUNT: dict[str, Decimal] = {"ARS": Decimal("1000000"), "USD": Decimal("10000")}

TOKEN_PATTERN = re.compile(r"^tok_[A-Za-z0-9_]{4,60}$")
PAN_LIKE = re.compile(r"\d{12,}")
MERCHANT_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


@dataclass(frozen=True)
class AuthorizationRequest:
    merchant_id: str
    amount: Decimal
    currency: str
    card_token: str


@dataclass(frozen=True)
class Decision:
    approved: bool
    response_code: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {"approved": self.approved, "response_code": self.response_code, "message": self.message}


def parse_request(data: Any) -> tuple[AuthorizationRequest | None, dict[str, str]]:
    """Valida el cuerpo de la solicitud. Devuelve (solicitud, {}) o (None, {campo: error})."""
    if not isinstance(data, dict):
        return None, {"body": "debe ser un objeto JSON"}

    errors: dict[str, str] = {}

    merchant_id = data.get("merchant_id")
    if not isinstance(merchant_id, str) or not MERCHANT_PATTERN.fullmatch(merchant_id):
        errors["merchant_id"] = "obligatorio; letras, números, guion o guion bajo (máx. 40)"

    currency = data.get("currency")
    if not isinstance(currency, str) or currency not in MAX_AMOUNT:
        errors["currency"] = f"obligatorio; una de: {', '.join(sorted(MAX_AMOUNT))}"

    amount = _parse_amount(data.get("amount"), errors)

    card_token = data.get("card_token")
    if not isinstance(card_token, str) or not card_token:
        errors["card_token"] = "obligatorio"
    elif PAN_LIKE.search(card_token):
        errors["card_token"] = "parece un número de tarjeta; envíe solo tokens (tok_...)"
    elif not TOKEN_PATTERN.fullmatch(card_token):
        errors["card_token"] = "formato inválido; se espera tok_ seguido de 4 a 60 caracteres"

    unknown = sorted(set(data) - {"merchant_id", "amount", "currency", "card_token"})
    if unknown:
        errors["body"] = f"campos no permitidos: {', '.join(unknown)}"

    if errors:
        return None, errors
    return AuthorizationRequest(merchant_id, amount, currency, card_token), {}  # type: ignore[arg-type]


def _parse_amount(value: Any, errors: dict[str, str]) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        errors["amount"] = "obligatorio; número mayor que 0"
        return None
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        errors["amount"] = "debe ser un número"
        return None
    if not amount.is_finite() or amount <= 0:
        errors["amount"] = "debe ser mayor que 0"
        return None
    if amount.as_tuple().exponent < -2:  # type: ignore[operator]
        errors["amount"] = "máximo 2 decimales"
        return None
    return amount
