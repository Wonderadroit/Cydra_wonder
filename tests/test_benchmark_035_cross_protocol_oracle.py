from pathlib import Path

from cydra.pipeline import investigate


def test_cross_protocol_readonly_hypothesis_gets_generic_planner():
    root = Path(__file__).resolve().parents[1]
    result = investigate(root / "benchmarks/035_cross_protocol_oracle/Target.sol")
    matches = [
        h for h in result.hypotheses
        if h.hypothesis_id == "H-READONLY-XCONTRACT-latestAnswer"
    ]
    assert matches
    experiment = next(e for e in result.experiments if e.hypothesis_id == matches[0].hypothesis_id)
    assert experiment.experiment_id == "X-H-READONLY-XCONTRACT-latestAnswer"
