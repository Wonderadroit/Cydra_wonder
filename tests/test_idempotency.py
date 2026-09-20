from pathlib import Path

from cydra.pipeline import investigate
from cydra.reasoning import plan_idempotency_experiment
from cydra.structural_idempotency import generate_idempotency_hypotheses


V = Path("benchmarks/011_idempotency_mt_pelerin/IdempotencyTarget.sol")
P = Path("benchmarks/011_idempotency_mt_pelerin/IdempotencyTargetPatched.sol")


def test_idempotency_detector_finds_repeated_record_transition():
    result = investigate(
        V,
        reasoning_surfaces=(generate_idempotency_hypotheses,),
        experiment_planner=plan_idempotency_experiment,
    )
    matches = [h for h in result.hypotheses if h.invariant_id.startswith("INV-IDEMPOTENCY-")]
    assert matches
    assert matches[0].target_function == "cancelOnHoldTransfers"


def test_idempotency_detector_does_not_flag_patched_counterpart():
    result = investigate(
        P,
        reasoning_surfaces=(generate_idempotency_hypotheses,),
        experiment_planner=plan_idempotency_experiment,
    )
    assert not [h for h in result.hypotheses if h.invariant_id.startswith("INV-IDEMPOTENCY-")]
