from __future__ import annotations

from .models import Experiment, Hypothesis


def plan_callback_state_order_experiment(hypothesis: Hypothesis) -> Experiment:
    return Experiment(
        experiment_id=f"X-{hypothesis.hypothesis_id}",
        hypothesis_id=hypothesis.hypothesis_id,
        action=(
            f"Execute {hypothesis.target_function} through a caller-controlled callback that "
            "reenters before the target's security-critical state update, then compare the "
            "reentrant outcome with the settled post-call state."
        ),
        discriminates=(
            "reentrant execution can exploit the pre-update state",
            "the state is established before the callback and the reentrant action is blocked",
        ),
        cost=2.0,
        planned_inputs=(),
        target_function=hypothesis.target_function,
    )
