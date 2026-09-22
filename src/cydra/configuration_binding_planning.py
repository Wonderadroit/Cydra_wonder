from __future__ import annotations

from .models import Experiment, Hypothesis


def plan_configuration_binding_experiment(hypothesis: Hypothesis) -> Experiment:
    return Experiment(
        experiment_id=f"X-{hypothesis.hypothesis_id}",
        hypothesis_id=hypothesis.hypothesis_id,
        action=(
            f"Execute {hypothesis.target_function} using a key that has not been registered "
            "and observe whether default configuration fields affect the operation; repeat "
            "against the patched target."
        ),
        discriminates=(
            "an unregistered configuration key is accepted and default values affect the result",
            "an unregistered configuration key is rejected before effectful use",
        ),
        cost=2.0,
        target_function=hypothesis.target_function,
    )
