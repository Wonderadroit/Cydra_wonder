from __future__ import annotations

from .models import Experiment, Hypothesis


def plan_external_outcome_experiment(hypothesis: Hypothesis) -> Experiment:
    return Experiment(
        experiment_id=f"X-{hypothesis.hypothesis_id}",
        hypothesis_id=hypothesis.hypothesis_id,
        action=(
            f"Execute {hypothesis.target_function} with an adversarial external dependency "
            "that reports failure while remaining callable, then observe whether the target "
            "continues into the subsequent state or value transition."
        ),
        discriminates=(
            "the transition stops when the external operation reports failure",
            "the transition continues despite the external operation reporting failure",
        ),
        cost=1.0,
        planned_inputs=(),
        target_function=hypothesis.target_function,
    )
