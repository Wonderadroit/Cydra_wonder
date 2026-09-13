from cydra.invariants import InvariantCandidate, CandidateVerification, VerificationState
from cydra.invariant_persistence import persist_invariant_verification
from cydra.system_model import Node, SystemModel


def test_invariant_verification_state_and_evidence_are_persisted():
    model = SystemModel()
    model.add_node(Node("evidence:e1", "evidence", "E1"))
    candidate = InvariantCandidate("candidate:c1", "function:f writes state:x", ("compiler:1",), 0.9, 1)
    verification = CandidateVerification("candidate:c1", VerificationState.SUPPORTED, ("evidence:e1",), ("evidence:e1",), (), 0.8)
    persist_invariant_verification(model, candidate, verification)
    assert model.nodes["candidate:c1"].attributes["verification_state"] == "supported"
    assert model.neighbors("candidate:c1", "verified_by") == ["evidence:e1"]
