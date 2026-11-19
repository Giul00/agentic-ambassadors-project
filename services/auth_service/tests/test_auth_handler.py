import base64
import json

from auth_service.handler import lambda_handler


def call(body, method="POST", v2=False, b64=False):
    raw = body if isinstance(body, str) else json.dumps(body)
    if b64:
        raw = base64.b64encode(raw.encode()).decode()
    event = {"body": raw, "isBase64Encoded": b64}
    if v2:
        event["requestContext"] = {"http": {"method": method}}
    else:
        event["httpMethod"] = method
    result = lambda_handler(event)
    return result["statusCode"], json.loads(result["body"])


GOOD = {"merchant_id": "m1", "amount": 100, "currency": "ARS", "card_token": "tok_demo01"}


def test_approved_response_shape():
    status, body = call(GOOD)
    assert status == 200
    assert body == {"approved": True, "response_code": "00", "message": "Aprobada"}


def test_declined_is_still_http_200():
    status, body = call({**GOOD, "card_token": "tok_blocked01"})
    assert status == 200 and body["response_code"] == "05" and body["approved"] is False


def test_http_api_v2_event():
    assert call(GOOD, v2=True)[0] == 200
    assert call(GOOD, v2=True, method="GET")[0] == 405


def test_base64_body():
    assert call(GOOD, b64=True)[1]["response_code"] == "00"


def test_invalid_json_is_400():
    status, body = call("{no es json")
    assert status == 400 and "JSON" in body["error"]


def test_validation_errors_are_400_with_details():
    status, body = call({**GOOD, "currency": "EUR"})
    assert status == 400 and "currency" in body["details"]


def test_empty_body_is_400():
    assert call("")[0] == 400


def test_get_is_405():
    assert call(GOOD, method="GET")[0] == 405


def test_too_large_body_is_413():
    assert call("x" * 20_000)[0] == 413


def test_bad_base64_is_400():
    event = {"httpMethod": "POST", "body": "%%%", "isBase64Encoded": True}
    assert lambda_handler(event)["statusCode"] == 400
