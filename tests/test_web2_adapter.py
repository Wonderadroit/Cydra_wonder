from __future__ import annotations

from cydra.execution_adapter import AdapterRequest, AdapterStatus
from cydra.web2_adapter import Web2Adapter, Web2Identity, Web2Target


def test_web2_adapter_fails_closed_without_authorization() -> None:
    try:
        Web2Adapter(Web2Target("https://example.com", ("example.com",), authorized=False))
    except PermissionError:
        return
    raise AssertionError("active Web2 execution must require explicit authorization")


def test_web2_adapter_keeps_identities_isolated() -> None:
    adapter = Web2Adapter(
        Web2Target("https://example.com", ("example.com",), authorized=True),
        identities={
            "alice": Web2Identity("alice", {"Authorization": "Bearer alice"}),
            "bob": Web2Identity("bob", {"Authorization": "Bearer bob"}),
        },
    )
    assert [item.name for item in adapter.capabilities()] == [
        "HTTP_REQUEST",
        "IDENTITY_SWITCH",
        "RESPONSE_OBSERVATION",
        "STATE_REPLAY",
    ]
    assert adapter._identities["alice"].headers["Authorization"] != adapter._identities["bob"].headers["Authorization"]


def test_unsupported_operation_is_not_security_evidence() -> None:
    adapter = Web2Adapter(
        Web2Target("https://example.com", ("example.com",), authorized=True)
    )
    result = adapter.execute(AdapterRequest("a1", "browser_magic"))
    assert result.status == AdapterStatus.UNAVAILABLE
    assert result.error
