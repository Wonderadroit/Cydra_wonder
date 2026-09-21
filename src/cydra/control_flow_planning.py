from __future__ import annotations

from .models import Experiment, Hypothesis


def plan_control_flow_experiment(hypothesis: Hypothesis) -> Experiment:
    return Experiment(
        experiment_id=f"X-{hypothesis.hypothesis_id}",
        hypothesis_id=hypothesis.hypothesis_id,
        action=(
            f"Reach {hypothesis.target_function} with a multi-element input where the first element "
            "already satisfies the loop's continue condition, then observe whether execution advances "
            "to the following element or exhausts its gas budget."
        ),
        discriminates=(
            "the continue branch preserves loop progress and later elements are processed",
            "the continue branch bypasses progress and execution cannot advance past the same element",
        ),
        cost=1.0,
        planned_inputs=(
            "at least two valid target elements",
            "first element pre-marked as already processed / continue condition true",
            "second element still requiring processing",
        ),
    )
