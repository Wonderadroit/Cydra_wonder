from cydra.hypothesis_selection import select_next_hypothesis
from cydra.models import Experiment, Hypothesis, Invariant


def test_selector_is_class_neutral_and_prefers_information_per_cost():
    invariant_a = Invariant("INV-A", "a", "test", 0.7)
    invariant_b = Invariant("INV-B", "b", "test", 0.9)
    h_a = Hypothesis("H-A", "a", "INV-A", "a", "caller", "impact", evidence_ids=("e1",))
    h_b = Hypothesis("H-B", "b", "INV-B", "b", "caller", "impact", evidence_ids=("e1", "e2"))
    e_a = Experiment("X-H-A", "H-A", "a", ("one",), 2.0)
    e_b = Experiment("X-H-B", "H-B", "b", ("one", "two"), 1.0)
    selected = select_next_hypothesis((h_a, h_b), (invariant_a, invariant_b), (e_a, e_b))
    assert selected.hypothesis.hypothesis_id == "H-B"


def test_selection_can_reject_a_contradicted_candidate_and_choose_the_next_one():
    invariant_a = Invariant("INV-A", "a", "test", 0.9)
    invariant_b = Invariant("INV-B", "b", "test", 0.8)
    h_a = Hypothesis("H-A", "a", "INV-A", "a", "caller", "impact")
    h_b = Hypothesis("H-B", "b", "INV-B", "b", "caller", "impact")
    e_a = Experiment("X-H-A", "H-A", "a", ("one",), 1.0)
    e_b = Experiment("X-H-B", "H-B", "b", ("one",), 1.0)

    selected = select_next_hypothesis(
        (h_a, h_b), (invariant_a, invariant_b), (e_a, e_b),
        excluded_hypothesis_ids=("H-A",),
    )

    assert selected.hypothesis.hypothesis_id == "H-B"


def test_selector_automatically_removes_explicitly_contradicted_hypothesis():
    invariant_a = Invariant("INV-A", "a", "test", 0.95)
    invariant_b = Invariant("INV-B", "b", "test", 0.8)
    h_a = Hypothesis("H-A", "a", "INV-A", "a", "caller", "impact")
    h_b = Hypothesis("H-B", "b", "INV-B", "b", "caller", "impact")
    e_a = Experiment("X-H-A", "H-A", "a", ("one",), 1.0)
    e_b = Experiment("X-H-B", "H-B", "b", ("one",), 1.0)

    selected = select_next_hypothesis(
        (h_a, h_b), (invariant_a, invariant_b), (e_a, e_b),
        observed_statuses={"H-A": "contradicted"},
    )
    assert selected.hypothesis.hypothesis_id == "H-B"


def test_ambiguous_observation_does_not_discard_a_hypothesis():
    invariant_a = Invariant("INV-A", "a", "test", 0.95)
    h_a = Hypothesis("H-A", "a", "INV-A", "a", "caller", "impact")
    e_a = Experiment("X-H-A", "H-A", "a", ("one",), 1.0)

    selected = select_next_hypothesis(
        (h_a,), (invariant_a,), (e_a,),
        observed_statuses={"H-A": "ambiguous"},
    )
    assert selected.hypothesis.hypothesis_id == "H-A"


def test_rejected_classifier_feedback_is_terminal_for_selection():
    invariant_a = Invariant("INV-A", "a", "test", 0.95)
    invariant_b = Invariant("INV-B", "b", "test", 0.8)
    h_a = Hypothesis("H-A", "a", "INV-A", "a", "caller", "impact")
    h_b = Hypothesis("H-B", "b", "INV-B", "b", "caller", "impact")
    e_a = Experiment("X-H-A", "H-A", "a", ("one",), 1.0)
    e_b = Experiment("X-H-B", "H-B", "b", ("one",), 1.0)

    selected = select_next_hypothesis(
        (h_a, h_b), (invariant_a, invariant_b), (e_a, e_b),
        observed_statuses={"H-A": "rejected"},
    )

    assert selected.hypothesis.hypothesis_id == "H-B"


def test_observed_nonterminal_hypothesis_remains_eligible_but_is_deprioritized():
    invariant_a = Invariant("INV-A", "a", "test", 0.95)
    invariant_b = Invariant("INV-B", "b", "test", 0.8)
    h_a = Hypothesis("H-A", "a", "INV-A", "a", "caller", "impact")
    h_b = Hypothesis("H-B", "b", "INV-B", "b", "caller", "impact")
    e_a = Experiment("X-H-A", "H-A", "a", ("one",), 1.0)
    e_b = Experiment("X-H-B", "H-B", "b", ("one",), 1.0)

    selected = select_next_hypothesis(
        (h_a, h_b), (invariant_a, invariant_b), (e_a, e_b),
        observed_statuses={"H-A": "proposed"},
    )

    assert selected.hypothesis.hypothesis_id == "H-B"


def test_evidence_density_does_not_outvote_a_fresher_more_discriminating_candidate():
    evidence_rich = Invariant("INV-RICH", "rich", "test", 0.82)
    fresh = Invariant("INV-FRESH", "fresh", "test", 0.86)
    h_rich = Hypothesis(
        "H-RICH", "rich", "INV-RICH", "rich", "caller", "impact",
        evidence_ids=("e1", "e2", "e3", "e4", "e5"),
    )
    h_fresh = Hypothesis("H-FRESH", "fresh", "INV-FRESH", "fresh", "caller", "impact")
    e_rich = Experiment("X-RICH", "H-RICH", "rich", ("one", "two"), 1.0)
    e_fresh = Experiment("X-FRESH", "H-FRESH", "fresh", ("one", "two"), 1.0)

    selected = select_next_hypothesis(
        (h_rich, h_fresh), (evidence_rich, fresh), (e_rich, e_fresh)
    )

    assert selected.hypothesis.hypothesis_id == "H-FRESH"
