from cydra.execution_adapter import AdapterRequest, AdapterStatus
from cydra.web2_adapter import Web2Adapter, Web2Identity, Web2Target

def test_active_execution_requires_explicit_authorization():
    try: Web2Adapter(Web2Target("https://example.com",("example.com",)))
    except PermissionError: return
    raise AssertionError("active Web2 execution must require explicit authorization")

def test_web2_adapter_keeps_identities_isolated():
    adapter=Web2Adapter(Web2Target("https://example.com",("example.com",),authorized=True),identities={"alice":Web2Identity("alice",{"Authorization":"Bearer alice"}),"bob":Web2Identity("bob",{"Authorization":"Bearer bob"})})
    assert [x.name for x in adapter.capabilities()]==["HTTP_REQUEST","IDENTITY_SWITCH","RESPONSE_OBSERVATION","STATE_REPLAY"]
    assert adapter._identities["alice"].headers["Authorization"] != adapter._identities["bob"].headers["Authorization"]

def test_unsupported_operation_is_not_security_evidence():
    result=Web2Adapter(Web2Target("https://example.com",("example.com",),authorized=True)).execute(AdapterRequest("a1","browser_magic"))
    assert result.status==AdapterStatus.UNAVAILABLE
