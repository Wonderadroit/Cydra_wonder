from cydra.hypotheses import Hypothesis,HypothesisState
from cydra.web2_causal import Web2CausalVerification
from cydra.web2_reasoning import apply_causal_verification,select_next_web2_experiment

def test_causal_verification_updates_hypothesis():
    h=Hypothesis("h1","non-owner can access owner resource"); v=Web2CausalVerification(HypothesisState.CAUSALLY_ESTABLISHED,0.95,"reproduced",("a",)); u=apply_causal_verification(h,v); assert u.state==HypothesisState.CAUSALLY_ESTABLISHED and u.belief==0.95

def test_selector_prefers_causal_replay():
    h=Hypothesis("h1","authorization must separate identities"); d=select_next_web2_experiment(h,has_differential_support=True,has_causal_verification=False,capability_gap=False); assert d.kind=="CAUSAL_REPLAY"

def test_selector_repairs_capability_first():
    h=Hypothesis("h1","authorization must separate identities"); d=select_next_web2_experiment(h,has_differential_support=True,has_causal_verification=False,capability_gap=True); assert d.kind=="CAPABILITY_REPAIR"
