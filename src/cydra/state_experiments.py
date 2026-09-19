from __future__ import annotations

from .experiment_planning import plan_experiment
from .experiment_inputs import conservative_defaults
from .models import ContractModel, Experiment, ExperimentStep, Hypothesis


def plan_cross_function_state_experiment(
    hypothesis: Hypothesis,
    peer_function: str | None = None,
    *,
    contract: ContractModel | None = None,
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

    if contract is not None:
        functions = {function.name: function for function in contract.functions}
        peer_model = functions.get(peer)
        target_model = functions.get(hypothesis.target_function)
        if peer_model is None or target_model is None:
            raise ValueError("state sequence function is absent from contract model")
        peer_defaults = conservative_defaults(peer_model.parameters)
        target_defaults = conservative_defaults(target_model.parameters)
        if peer_defaults is None or target_defaults is None:
            raise ValueError("state sequence contains unsupported parameter type")
        first_arguments = tuple(peer_defaults[p.name] for p in peer_model.parameters)
        second_arguments = tuple(target_defaults[p.name] for p in target_model.parameters)
    else:
        first_arguments = (first_input,)
        second_arguments = (second_input,)

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
        (ExperimentStep(peer, first_arguments), ExperimentStep(hypothesis.target_function, second_arguments)),
    )
