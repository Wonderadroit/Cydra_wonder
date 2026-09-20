from __future__ import annotations

from .models import Experiment, Hypothesis


def plan_signature_reuse_experiment(hypothesis: Hypothesis) -> Experiment:
    return Experiment(
        experiment_id=f"X-{hypothesis.hypothesis_id}",
        hypothesis_id=hypothesis.hypothesis_id,
        action=f"Execute {hypothesis.target_function} with one valid signed authorization, then submit the exact same authorization again and compare whether the second state transition is accepted.",
        discriminates=(
            "the authorization is consumed exactly once",
            "the same authorization can trigger the state-changing operation repeatedly",
        ),
        cost=1.0,
        planned_inputs=("one valid signed authorization", "same authorization submitted twice", "same target and signer"),
    )
