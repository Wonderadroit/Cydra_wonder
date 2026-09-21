from pathlib import Path
from cydra.pipeline import investigate

def test_incentive_liveness_hypothesis_is_generic():
    root=Path(__file__).resolve().parents[1]
    result=investigate(root/"benchmarks/036_incentive_state_divergence/Target.sol")
    matches=[h for h in result.hypotheses if h.hypothesis_id=="H-INCENTIVE-LIVENESS-commitWork"]
    assert matches
    experiment=next(e for e in result.experiments if e.hypothesis_id==matches[0].hypothesis_id)
    assert experiment.experiment_id=="X-H-INCENTIVE-LIVENESS-commitWork"
