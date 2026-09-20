from pathlib import Path

from cydra.pipeline import investigate


def test_read_only_reentrancy_discovers_transient_view_hypothesis():
    target = Path(__file__).parents[1] / "benchmarks/012_read_only_reentrancy/ReadOnlyReentrancyTarget.sol"
    result = investigate(target)
    hypotheses = [h for h in result.hypotheses if h.invariant_id.startswith("INV-READONLY-REENTRANCY-")]
    assert hypotheses
    hypothesis = hypotheses[0]
    assert hypothesis.target_function == "removeLiquidity"
    assert hypothesis.related_functions == ("virtualPrice",)
    experiment = next(e for e in result.experiments if e.hypothesis_id == hypothesis.hypothesis_id)
    assert experiment.planned_inputs == ("10",)
