from cydra.execution_adapter import AdapterObservation,AdapterStatus
from cydra.invariants import VerificationRole
from cydra.hypotheses import Hypothesis
from cydra.web2_evidence import authorization_differential_evidence

def h(): return Hypothesis("H-WEB2-AUTH-EVIDENCE","owner and non-owner should have distinct authorization outcomes",invariant_id="I-AUTH",target_function="GET /records/1",attacker_capability="authenticated non-owner",expected_impact="UNAUTHORIZED_RESOURCE_ACCESS")
def o(a,s,b): return AdapterObservation(AdapterStatus.EXECUTED,a,{"status_code":s,"body_sha256":b})

def test_identical_response_contradicts():
    assert authorization_differential_evidence(h(),(o("owner",200,"same"),o("comparison",200,"same")))[0].role==VerificationRole.CONTRADICTS

def test_different_outcomes_support():
    assert authorization_differential_evidence(h(),(o("owner",200,"owner"),o("comparison",403,"denied")))[0].role==VerificationRole.SUPPORTS

def test_capability_failure_is_neutral():
    assert authorization_differential_evidence(h(),(o("owner",200,"owner"),AdapterObservation(AdapterStatus.UNAVAILABLE,"comparison",error="missing")))[0].role==VerificationRole.NEUTRAL
