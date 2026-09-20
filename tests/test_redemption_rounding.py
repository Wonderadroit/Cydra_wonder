from pathlib import Path
from cydra.pipeline import investigate

def test_redemption_rounding_is_inferred_from_source_topology():
    root=Path(__file__).resolve().parents[1]
    result=investigate(root/"benchmarks/014_redemption_rounding/RedemptionRoundingTarget.sol")
    matches=[h for h in result.hypotheses if h.invariant_id.startswith("INV-REDEMPTION-ROUNDING-")]
    assert len(matches)==1
    assert matches[0].target_function=="redeemUnderlying"
    experiment=next(e for e in result.experiments if e.hypothesis_id==matches[0].hypothesis_id)
    assert experiment.planned_inputs==("3",)

def test_redemption_rounding_does_not_flag_patched_counterpart():
    root=Path(__file__).resolve().parents[1]
    result=investigate(root/"benchmarks/014_redemption_rounding/RedemptionRoundingTargetPatched.sol")
    assert not [h for h in result.hypotheses if h.invariant_id.startswith("INV-REDEMPTION-ROUNDING-")]
