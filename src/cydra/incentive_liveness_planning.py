from __future__ import annotations
from .models import Experiment, Hypothesis

def plan_incentive_liveness_experiment(hypothesis: Hypothesis) -> Experiment:
    return Experiment(
        experiment_id="X-"+hypothesis.hypothesis_id,
        hypothesis_id=hypothesis.hypothesis_id,
        target_function=hypothesis.target_function,
        steps=(),
        expected_observation=hypothesis.expected_observation,
        rationale="compare caller cost required to manufacture payout-eligible work with the resulting incentive payout",
    )
