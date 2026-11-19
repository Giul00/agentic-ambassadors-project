from decimal import Decimal

import pytest

from auth_service.models import AuthorizationRequest, Decision, parse_request
from auth_service.rules import RESPONSE_CODES, authorize, decline, default_rules


def req(amount="100", currency="ARS", token="tok_demo01", merchant="m1"):
    return AuthorizationRequest(merchant, Decimal(amount), currency, token)


def valid_body(**overrides):
    body = {"merchant_id": "m1", "amount": 100, "currency": "ARS", "card_token": "tok_demo01"}
    body.update(overrides)
    return body


# --- reglas -----------------------------------------------------------------

def test_normal_request_is_approved():
    assert authorize(req()) == Decision(True, "00", "Aprobada")


def test_blocked_token_is_declined_05():
    assert authorize(req(token="tok_blocked01")).response_code == "05"


@pytest.mark.parametrize("currency,limit", [("ARS", "1000000"), ("USD", "10000")])
def test_amount_limit(currency, limit):
    assert authorize(req(amount=limit, currency=currency)).approved
    over = authorize(req(amount=str(Decimal(limit) + Decimal("0.01")), currency=currency))
    assert over.response_code == "61" and not over.approved


def test_low_balance_token():
    assert authorize(req(amount="100", token="tok_lowbal_a")).approved
    assert authorize(req(amount="100.01", token="tok_lowbal_a")).response_code == "51"


def test_first_declining_rule_wins():
    # bloqueada y además excede el monto: gana la regla de tarjeta bloqueada (va primero)
    assert authorize(req(amount="99999999", token="tok_blocked01")).response_code == "05"


def test_custom_rules_are_used_instead_of_defaults():
    always_decline = lambda r: decline("05")
    assert authorize(req(), rules=[always_decline]).response_code == "05"
    assert authorize(req(token="tok_blocked01"), rules=[]).approved


def test_every_decline_code_has_a_message():
    for rule in default_rules():
        assert callable(rule)
    assert all(RESPONSE_CODES[c] for c in ("00", "05", "51", "61"))


# --- validación -------------------------------------------------------------

def test_valid_body_parses():
    parsed, errors = parse_request(valid_body(amount="250.50"))
    assert errors == {}
    assert parsed.amount == Decimal("250.50")


@pytest.mark.parametrize(
    "field,value",
    [
        ("merchant_id", ""),
        ("merchant_id", "con espacios"),
        ("amount", 0),
        ("amount", -5),
        ("amount", "abc"),
        ("amount", True),
        ("amount", "1.001"),
        ("amount", "NaN"),
        ("currency", "EUR"),
        ("card_token", "tok_x"),
        ("card_token", "4111111111111111"),
        ("card_token", "tok_4111111111111111"),
    ],
)
def test_invalid_field_is_reported(field, value):
    parsed, errors = parse_request(valid_body(**{field: value}))
    assert parsed is None and field in errors


def test_missing_fields_are_all_reported():
    parsed, errors = parse_request({})
    assert parsed is None
    assert set(errors) == {"merchant_id", "amount", "currency", "card_token"}


def test_unknown_fields_are_rejected():
    parsed, errors = parse_request(valid_body(cvv="123"))
    assert parsed is None and "cvv" in errors["body"]


def test_non_object_body():
    assert parse_request([1, 2])[1] == {"body": "debe ser un objeto JSON"}


def test_pan_like_token_message_does_not_echo_value():
    _, errors = parse_request(valid_body(card_token="4111111111111111"))
    assert "4111" not in errors["card_token"]
