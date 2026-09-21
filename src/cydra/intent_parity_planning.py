from __future__ import annotations

from .models import Experiment, Hypothesis


def plan_intent_parity_experiment(hypothesis: Hypothesis) -> Experiment:
    return Experiment(
        experiment_id=f"X-INTENT-PARITY-{hypothesis.target_function}",
        hypothesis_id=hypothesis.hypothesis_id,
        target_function=hypothesis.target_function,
        discriminates=("documented role is accepted", "narrow modifier rejects documented caller"),
        cost=1.0,
        planned_inputs=(),
    )
