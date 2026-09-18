from __future__ import annotations

from .experiment_planning import plan_experiment
from .models import Experiment, Hypothesis


def plan_cross_function_state_experiment(
    hypothesis: Hypothesis,
    peer_function: str,
    *,
    first_input: str = "1",
    second_input: str = "1",
) -> Experiment:
    """Plan an ordered cross-function state-transition experiment.

    The planner is deliberately class-neutral. It does not assume deposit,
    withdraw, balances, accounting, or any benchmark-specific function name.
    The reasoning surface supplies the target and an observed peer transition;
    this layer preserves the sequence as the causal experiment to execute.
    """
    if not peer_function.strip():
        raise ValueError("peer function must not be empty")
    if peer_function == hypothesis.target_function:
        raise ValueError("peer function must differ from target function")
    if not first_input.strip() or not second_input.strip():
        raise ValueError("sequence inputs must not be empty")

    return plan_experiment(
        hypothesis,
        (
            f"Execute {peer_function}({first_input}) then "
            f"{hypothesis.target_function}({second_input}) as an arbitrary external caller; "
            "observe the modeled shared state before, between, and after transitions; "
            "repeat the identical ordered sequence against the patched target."
        ),
        (
            "the ordered composition violates the modeled shared-state relation",
            "the ordered composition preserves the modeled shared-state relation",
        ),
        2.0,
    )
