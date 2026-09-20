from __future__ import annotations

from .models import Experiment, Hypothesis


def plan_epoch_accounting_experiment(hypothesis: Hypothesis) -> Experiment:
    return Experiment(
        experiment_id=f"X-{hypothesis.hypothesis_id}",
        hypothesis_id=hypothesis.hypothesis_id,
        action=(
            f"Execute {hypothesis.target_function} from a checkpoint inside one epoch across the next epoch boundary, "
            "then compare accumulated accounting with the piecewise sum implied by each configured epoch rate."
        ),
        discriminates=(
            "accounting uses the configured rate for exactly each interval",
            "one epoch rate is applied across an epoch boundary",
        ),
        cost=2.0,
        planned_inputs=("unaligned prior checkpoint", "next aligned epoch boundary", "following epoch"),
        target_function=hypothesis.target_function,
    )
