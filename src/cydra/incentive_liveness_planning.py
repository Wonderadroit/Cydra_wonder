from __future__ import annotations

from .models import Experiment, Hypothesis


def plan_incentive_liveness_experiment(hypothesis: Hypothesis) -> Experiment:
    return Experiment(
        experiment_id="X-" + hypothesis.hypothesis_id,
        hypothesis_id=hypothesis.hypothesis_id,
        action=hypothesis.target_function,
        discriminates=(
            "caller cost required to create payout-eligible work",
            "payout received by the caller",
        ),
        cost=1.0,
        target_function=hypothesis.target_function,
        steps=(),
    )
