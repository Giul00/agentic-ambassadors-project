"""Reglas de decisión de auth-service.

Cada regla recibe la solicitud y devuelve una Decision de rechazo, o None si no aplica.
Las reglas se evalúan en orden; la primera que rechaza decide. Si ninguna rechaza, se aprueba.

Para agregar una regla: escribir la función, sumar su código a RESPONSE_CODES y agregarla a
default_rules(). Si la regla necesita estado (por ejemplo, contar solicitudes), recibirlo por
parámetro para poder probarla sin AWS.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Callable, Iterable

from .models import MAX_AMOUNT, AuthorizationRequest, Decision

Rule = Callable[[AuthorizationRequest], "Decision | None"]

# Códigos de respuesta ISO 8583 usados por el servicio.
RESPONSE_CODES: dict[str, str] = {
    "00": "Aprobada",
    "05": "No aprobada",
    "51": "Fondos insuficientes",
    "61": "Excede el límite de monto",
}

# Tokens sintéticos con comportamiento fijo, para pruebas y demo.
BLOCKED_TOKENS = frozenset({"tok_blocked01"})
LOW_BALANCE_PREFIX = "tok_lowbal"
LOW_BALANCE_LIMIT = Decimal("100")


def decline(code: str) -> Decision:
    return Decision(approved=False, response_code=code, message=RESPONSE_CODES[code])


def blocked_card(req: AuthorizationRequest) -> Decision | None:
    return decline("05") if req.card_token in BLOCKED_TOKENS else None


def amount_limit(req: AuthorizationRequest) -> Decision | None:
    return decline("61") if req.amount > MAX_AMOUNT[req.currency] else None


def low_balance(req: AuthorizationRequest) -> Decision | None:
    if req.card_token.startswith(LOW_BALANCE_PREFIX) and req.amount > LOW_BALANCE_LIMIT:
        return decline("51")
    return None


def default_rules() -> list[Rule]:
    return [blocked_card, amount_limit, low_balance]


def authorize(req: AuthorizationRequest, rules: Iterable[Rule] | None = None) -> Decision:
    for rule in default_rules() if rules is None else rules:
        decision = rule(req)
        if decision is not None:
            return decision
    return Decision(approved=True, response_code="00", message=RESPONSE_CODES["00"])
