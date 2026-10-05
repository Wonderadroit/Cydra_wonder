from dataclasses import dataclass

from cydra.execution_adapter import AdapterObservation, AdapterStatus
from cydra.hypotheses import Hypothesis, HypothesisState
from cydra.web2_causal import verify_reproducible_authorization_bypass
from cydra.web2_model import Web2IdentityModel, Web2ResourceModel, Web2TargetModel


def model():
    m = Web2TargetModel("https://authorized.example")
    m.add_identity(Web2IdentityModel("alice", "owner"))
    m.add_identity(Web2IdentityModel("bob", "comparison"))
    m.add_resource(Web2ResourceModel("record-1", "private record", "alice", "1"))
    return m


def obs(action_id, status=200, body="secret"):
    return AdapterObservation(
        AdapterStatus.EXECUTED, action_id,
        {"status_code": status, "body_sha256": body},
    )


def test_reproducible_owner_and_non_owner_access_becomes_causal():
    result = verify_reproducible_authorization_bypass(
        model(),
        hypothesis=Hypothesis("web2-auth:record-1:get", "non-owner must not receive the owner-only resource"),
        resource_id="record-1",
        owner_observations=(obs("owner-1"), obs("owner-2")),
        comparison_observations=(obs("other-1"), obs("other-2")),
    )
    assert result.state == HypothesisState.CAUSALLY_ESTABLISHED
    assert result.confidence == 0.95


def test_causal_replay_stays_unresolved_on_adapter_failure():
    failed = AdapterObservation(AdapterStatus.UNAVAILABLE, "other-2")
    result = verify_reproducible_authorization_bypass(
        model(),
        hypothesis=Hypothesis("web2-auth:record-1:get", "non-owner must not receive the owner-only resource"),
        resource_id="record-1",
        owner_observations=(obs("owner-1"), obs("owner-2")),
        comparison_observations=(obs("other-1"), failed),
    )
    assert result.state == HypothesisState.UNRESOLVED
