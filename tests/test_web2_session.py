import base64
import json

from cydra.web2_session import Web2Session


def test_session_from_base64_preserves_auth_material_without_artifact_shape():
    payload = {
        "version": 1,
        "session_id": "owner",
        "target_origin": "https://app.example",
        "headers": {"Authorization": "Bearer secret"},
        "cookies": [
            {
                "name": "session",
                "value": "cookie-secret",
                "domain": "app.example",
            }
        ],
    }
    encoded = base64.b64encode(json.dumps(payload).encode()).decode()
    session = Web2Session.from_base64(encoded, default_target_origin="https://app.example")

    assert session.authenticated
    assert session.headers["Authorization"] == "Bearer secret"
    assert session.cookies[0].value == "cookie-secret"


def test_session_rejects_cookie_outside_target():
    payload = {
        "version": 1,
        "session_id": "owner",
        "target_origin": "https://app.example",
        "cookies": [{"name": "session", "value": "x", "domain": "evil.example"}],
    }
    session = Web2Session.from_mapping(payload, default_target_origin="https://app.example")
    try:
        session.validate_for("https://app.example", ("app.example",))
    except PermissionError:
        return
    raise AssertionError("out-of-scope session cookie must fail closed")


def test_session_accepts_subdomain_cookie_for_allowlisted_target():
    payload = {
        "version": 1,
        "session_id": "owner",
        "target_origin": "https://app.example",
        "cookies": [{"name": "session", "value": "x", "domain": ".example"}],
    }
    session = Web2Session.from_mapping(payload, default_target_origin="https://app.example")
    session.validate_for("https://app.example", ("app.example",))
