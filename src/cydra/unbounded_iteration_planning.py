from __future__ import annotations
from .models import Experiment, Hypothesis


def plan_unbounded_iteration_experiment(hypothesis: Hypothesis) -> Experiment:
    return Experiment(
        experiment_id=f"X-{hypothesis.hypothesis_id}",
        hypothesis_id=hypothesis.hypothesis_id,
        action=(
            f"invoke {hypothesis.target_function} across increasing collection sizes "
            "and measure whether the critical path remains executable"
        ),
        discriminates=(
            "collection size is caller-influenced",
            "execution remains successful at baseline size",
            "execution fails or exceeds the configured execution budget after growth",
        ),
        cost=2.0,
    )
