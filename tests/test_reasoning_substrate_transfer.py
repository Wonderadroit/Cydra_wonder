from cydra.belief_reasoning import apply_verification
from cydra.hypotheses import Hypothesis, HypothesisState
from cydra.information_gain import rank_next_observations
from cydra.invariants import VerificationEvidence, VerificationRole, CandidateVerification, VerificationState
from cydra.invariant_reasoning import derive_invariant_candidates
from cydra.system_model import Node, SystemModel
from cydra.test_planning import ObservationOption


def test_invariant_candidates_are_derived_from_evidence_backed_graph_edges():
    model = SystemModel()
    model.add_node(Node("function:C:f", "function", "f"))
    model.add_node(Node("state:C:x", "state_variable", "x"))
    model.connect("function:C:f", "writes", "state:C:x", evidence_backed=True, candidate=True, provenance="compiler", confidence=0.9, ast_node_id=12)
    candidates = derive_invariant_candidates(model)
    assert len(candidates) == 1
    assert candidates[0].source_ids == ("compiler:12",)


def test_belief_update_preserves_explicit_support():
    hypothesis = Hypothesis("H1", "f can mutate privileged state")
    evidence = (VerificationEvidence("E1", VerificationRole.SUPPORTS, 0.8),)
    verification = CandidateVerification("C1", VerificationState.SUPPORTED, ("E1",), ("E1",), (), 0.8)
    updated, record = apply_verification(hypothesis, verification, evidence)
    assert updated.state is HypothesisState.SUPPORTED
    assert updated.belief > hypothesis.belief
    assert record.evidence_ids == ("E1",)


def test_information_gain_planning_only_ranks_observations():
    hypotheses = (
        Hypothesis("H1", "A", belief=0.5, planning_predictions={"O1": {"supports": 1.0, "contradicts": 0.0}}),
        Hypothesis("H2", "B", belief=0.5, planning_predictions={"O1": {"supports": 0.0, "contradicts": 1.0}}),
    )
    observations = (
        ObservationOption("O1", "distinguishing observation", ("supports", "contradicts"), 1.0),
        ObservationOption("O2", "single outcome", ("unknown",), 1.0),
    )
    plans = rank_next_observations(hypotheses, observations)
    assert plans[0].observation_id == "O1"
    assert plans[0].information_gain > plans[1].information_gain
