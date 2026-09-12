from cydra.invariant_hypothesis_bridge import hypotheses_from_verified_invariants, persist_invariant_hypotheses
from cydra.invariants import InvariantCandidate, VerificationState
from cydra.system_model import Node, SystemModel


def test_only_explicitly_supported_invariants_become_hypotheses():
    model = SystemModel()
    supported = InvariantCandidate("candidate:supported", "f writes x", ("compiler:1",), 0.9, 1)
    unresolved = InvariantCandidate("candidate:unresolved", "f writes y", ("compiler:2",), 0.8, 1)
    model.add_node(Node("candidate:supported", "invariant", supported.statement, {"verification_state": VerificationState.SUPPORTED.value, "verification_confidence": 0.9}))
    model.add_node(Node("candidate:unresolved", "invariant", unresolved.statement, {"verification_state": VerificationState.UNRESOLVED.value, "verification_confidence": 0.8}))
    hypotheses = hypotheses_from_verified_invariants(model, (supported, unresolved))
    assert [item.invariant_id for item in hypotheses] == ["candidate:supported"]
    persist_invariant_hypotheses(model, hypotheses)
    assert model.nodes["hypothesis:candidate:supported"].kind == "hypothesis"
    assert model.neighbors("candidate:supported", "informs") == ["hypothesis:candidate:supported"]
