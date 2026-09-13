from cydra.invariants import InvariantCandidate, VerificationEvidence, VerificationRole
from cydra.reasoning_pipeline import verify_and_bind_invariants
from cydra.system_model import SystemModel


def test_reasoning_pipeline_promotes_only_supported_invariants():
    model = SystemModel()
    candidates = (
        InvariantCandidate("candidate:supported", "f writes x", ("compiler:1",), 0.9, 1),
        InvariantCandidate("candidate:unresolved", "g writes y", ("compiler:2",), 0.8, 1),
    )
    hypotheses = verify_and_bind_invariants(
        model,
        candidates,
        {"candidate:supported": (VerificationEvidence("e1", VerificationRole.SUPPORTS, 0.9),)},
    )
    assert [item.invariant_id for item in hypotheses] == ["candidate:supported"]
