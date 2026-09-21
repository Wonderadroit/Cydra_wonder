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


def test_selection_rewards_actionable_executable_experiments():
    h1 = Hypothesis("H-ACTION-A", "cheap but unbound", "INV-ACTION-A", "f", "actor", "impact", evidence_ids=("E-A",))
    h2 = Hypothesis("H-ACTION-B", "slightly more costly but executable", "INV-ACTION-B", "g", "actor", "impact", evidence_ids=("E-B",))
    i1 = Invariant("INV-ACTION-A", "a", "test", 0.82)
    i2 = Invariant("INV-ACTION-B", "b", "test", 0.86)
    e1 = Experiment("X-ACTION-A", "H-ACTION-A", "call f", ("x", "y"), 1.0, ())
    e2 = Experiment("X-ACTION-B", "H-ACTION-B", "call g", ("x", "y"), 2.0, ("1", "2"))
    selected = select_next_hypothesis((h1, h2), (i1, i2), (e1, e2))
    assert selected.hypothesis.hypothesis_id == "H-ACTION-B"
