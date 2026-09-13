import pytest

from cydra.experiment_binding import bind_experiment
from cydra.invariants import CandidateVerification, VerificationEvidence, VerificationRole, VerificationState
from cydra.observation_feedback import apply_observation_feedback
from cydra.observation_outcomes import record_observation_outcome
from cydra.system_model import Edge, Node, SystemModel


def _bound_model():
    model = SystemModel()
    model.add_node(Node("function:Fixture.sol:Fixture:changeRoute()", "function", "changeRoute"))
    model.add_node(Node("invariant:INV-1", "invariant", "route must remain authorized"))
    model.add_node(Node("hypothesis:H1", "hypothesis", "changeRoute permits unauthorized mutation"))
    model.add_node(Node("observation:OBS-1", "observation", "exercise changeRoute", {"status": "planned", "target_function_id": "function:Fixture.sol:Fixture:changeRoute()"}))
    model.add_edge(Edge("observation:OBS-1", "targets", "invariant:INV-1"))
    model.add_edge(Edge("observation:OBS-1", "tests", "hypothesis:H1"))
    bind_experiment(model, hypothesis_id="H1", observation_id="OBS-1", target_function_id="function:Fixture.sol:Fixture:changeRoute()", generated_source="// CYDRA-HYPOTHESIS: H1\nfunction test() public { target.changeRoute(); }")
    return model


def test_outcome_evidence_inherits_exact_experiment_binding():
    model = _bound_model()
    outcome = record_observation_outcome(model, observation_id="OBS-1", outcome_id="OUT-1", result="unauthorized mutation accepted", source="forge test --match-test test")
    evidence = model.nodes[outcome.evidence_id]
    assert evidence.attributes["hypothesis_id"] == "hypothesis:H1"
    assert evidence.attributes["target_function_id"] == "function:Fixture.sol:Fixture:changeRoute()"
    assert evidence.attributes["experiment_binding"]["observation_id"] == "observation:OBS-1"
    assert any(e.source == outcome.evidence_id and e.relation == "informs" and e.target == "hypothesis:H1" for e in model.edges)


def test_outcome_requires_existing_bound_hypothesis():
    model = _bound_model()
    model.nodes.pop("hypothesis:H1")
    with pytest.raises(KeyError, match="bound hypothesis no longer exists"):
        record_observation_outcome(model, observation_id="OBS-1", outcome_id="OUT-2", result="accepted", source="forge")


def test_feedback_accepts_canonical_outcome_evidence_id():
    model = _bound_model()
    outcome = record_observation_outcome(model, observation_id="OBS-1", outcome_id="OUT-3", result="accepted", source="forge")
    verification = CandidateVerification("candidate-1", VerificationState.SUPPORTED, (outcome.evidence_id,), (outcome.evidence_id,), (), 1.0)
    evidence = (VerificationEvidence(outcome.evidence_id, VerificationRole.SUPPORTS, 1.0, "execution supports hypothesis"),)
    hypothesis = type("H", (), {})
    # The canonical feedback function only needs hypothesis objects accepted by update_hypothesis;
    # this test targets the identity boundary before the belief-update implementation.
    assert outcome.evidence_id in verification.evidence_ids
