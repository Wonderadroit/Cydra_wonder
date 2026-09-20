from __future__ import annotations
from .models import Experiment, Hypothesis

def plan_signature_replay_experiment(hypothesis: Hypothesis) -> Experiment:
    return Experiment(
        experiment_id=f"X-{hypothesis.hypothesis_id}",
        hypothesis_id=hypothesis.hypothesis_id,
        action=f"Execute {hypothesis.target_function} with one valid authorization, then repeat the same authorization against a distinct execution domain and compare acceptance.",
        discriminates=(
            "the authorization is bound to one execution domain",
            "the same authorization remains valid outside that domain",
        ),
        cost=1.0,
        planned_inputs=("same signed message", "same signer", "distinct deployment or chain context"),
    )
