from pathlib import Path

from cydra.pipeline import investigate


def test_keeper_zero_work_incentive_hypothesis_is_generic():
    root = Path(__file__).resolve().parents[1]
    result = investigate(root / "benchmarks/037_keeper_zero_work_incentive/Target.sol")
    matches = [
        h
        for h in result.hypotheses
        if h.hypothesis_id == "H-INCENTIVE-LIVENESS-settle"
    ]
    assert matches
    experiment = next(
        e for e in result.experiments if e.hypothesis_id == matches[0].hypothesis_id
    )
    assert experiment.experiment_id == "X-H-INCENTIVE-LIVENESS-settle"
