from cydra.execution_adapter import AdapterObservation,AdapterStatus
from cydra.hypotheses import Hypothesis,HypothesisState
from cydra.web2_causal import verify_reproducible_authorization_bypass
from cydra.web2_model import Web2IdentityModel,Web2ResourceModel,Web2TargetModel

def model():
    m=Web2TargetModel("https://authorized.example"); m.add_identity(Web2IdentityModel("alice","owner")); m.add_identity(Web2IdentityModel("bob","comparison")); m.add_resource(Web2ResourceModel("record-1","private","alice","1")); return m
def o(a,s=200,b="secret"): return AdapterObservation(AdapterStatus.EXECUTED,a,{"status_code":s,"body_sha256":b})

def test_reproducible_access_becomes_causal():
    r=verify_reproducible_authorization_bypass(model(),hypothesis=Hypothesis("web2-auth:record-1:get","non-owner must not receive owner-only resource"),resource_id="record-1",owner_observations=(o("owner-1"),o("owner-2")),comparison_observations=(o("other-1"),o("other-2")))
    assert r.state==HypothesisState.CAUSALLY_ESTABLISHED and r.confidence==0.95

def test_causal_replay_failure_stays_unresolved():
    failed=AdapterObservation(AdapterStatus.UNAVAILABLE,"other-2")
    r=verify_reproducible_authorization_bypass(model(),hypothesis=Hypothesis("web2-auth:record-1:get","x"),resource_id="record-1",owner_observations=(o("owner-1"),o("owner-2")),comparison_observations=(o("other-1"),failed))
    assert r.state==HypothesisState.UNRESOLVED
