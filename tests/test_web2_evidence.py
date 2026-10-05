from cydra.execution_adapter import AdapterObservation, AdapterStatus
from cydra.invariants import VerificationRole
from cydra.hypotheses import Hypothesis
from cydra.web2_evidence import authorization_differential_evidence


def hypothesis() -> Hypothesis:
    return Hypothesis(
        hypothesis_id="H-WEB2-AUTH-EVIDENCE",
        statement="owner and non-owner should have distinct authorization outcomes",
        invariant_id="I-AUTH",
        target_function="GET /records/1",
        attacker_capability="authenticated non-owner",
        expected_impact="UNAUTHORIZED_RESOURCE_ACCESS",
    )


def obs(action_id, status, body_hash):
    return AdapterObservation(
        AdapterStatus.EXECUTED,
        action_id,
        value={"status_code": status, "body_sha256": body_hash},
    )


def test_identical_owner_and_non_owner_response_contradicts_expected_separation():
    evidence = authorization_differential_evidence(
        hypothesis(),
        (obs("owner", 200, "same"), obs("comparison", 200, "same")),
    )
    assert evidence[0].role == VerificationRole.CONTRADICTS


def test_different_authorization_outcomes_support_modeled_separation():
    evidence = authorization_differential_evidence(
        hypothesis(),
        (obs("owner", 200, "owner"), obs("comparison", 403, "denied")),
    )
    assert evidence[0].role == VerificationRole.SUPPORTS


def test_capability_failure_is_neutral():
    evidence = authorization_differential_evidence(
        hypothesis(),
        (obs("owner", 200, "owner"), AdapterObservation(
            AdapterStatus.UNAVAILABLE, "comparison", error="missing capability"
        )),
    )
    assert evidence[0].role == VerificationRole.NEUTRAL
