from __future__ import annotations

from .experiment_planning import plan_experiment
from .models import Experiment, ExperimentStep, Hypothesis


def plan_cross_function_state_experiment(
    hypothesis: Hypothesis,
    peer_function: str | None = None,
    *,
    first_input: str = "1",
    second_input: str = "1",
) -> Experiment:
    """Plan an ordered cross-function state-transition experiment.

    The planner is deliberately class-neutral. It does not assume deposit,
    withdraw, balances, accounting, or any benchmark-specific function name.
    The reasoning surface supplies the target and, when available, related
    transitions; this layer preserves the sequence as the causal experiment.
    """
    peer = peer_function
    if peer is None:
        if not hypothesis.related_functions:
            raise ValueError("state hypothesis has no related transition")
        peer = hypothesis.related_functions[0]

    if not peer.strip():
        raise ValueError("peer function must not be empty")
    if peer == hypothesis.target_function:
        raise ValueError("peer function must differ from target function")
    if not first_input.strip() or not second_input.strip():
        raise ValueError("sequence inputs must not be empty")

    experiment = plan_experiment(
        hypothesis,
        (
            f"Execute {peer}({first_input}) then "
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
    return Experiment(
        experiment.experiment_id,
        experiment.hypothesis_id,
        experiment.action,
        experiment.discriminates,
        experiment.cost,
        experiment.planned_inputs,
        experiment.target_function,
        (ExperimentStep(peer, (first_input,)), ExperimentStep(hypothesis.target_function, (second_input,))),
    )
