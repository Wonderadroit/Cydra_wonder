from cydra.hypotheses import Hypothesis, HypothesisState
from cydra.web2_causal import Web2CausalVerification
from cydra.web2_reasoning import apply_causal_verification, select_next_web2_experiment


def test_causal_verification_updates_hypothesis():
    h = Hypothesis("h1", "non-owner can access owner resource")
    v = Web2CausalVerification(HypothesisState.CAUSALLY_ESTABLISHED, 0.95, "reproduced", ("a",))
    updated = apply_causal_verification(h, v)
    assert updated.state == HypothesisState.CAUSALLY_ESTABLISHED
    assert updated.belief == 0.95


def test_selector_prefers_causal_replay_before_impact():
    h = Hypothesis("h1", "authorization must separate identities")
    decision = select_next_web2_experiment(h, has_differential_support=True, has_causal_verification=False, capability_gap=False)
    assert decision.kind == "CAUSAL_REPLAY"


def test_selector_repairs_capability_before_security_reasoning():
    h = Hypothesis("h1", "authorization must separate identities")
    decision = select_next_web2_experiment(h, has_differential_support=True, has_causal_verification=False, capability_gap=True)
    assert decision.kind == "CAPABILITY_REPAIR"
