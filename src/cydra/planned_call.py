from __future__ import annotations

from .experiment_inputs import conservative_defaults
from .models import Experiment, FunctionModel, ParameterModel


def conservative_argument(parameter: ParameterModel) -> str:
    """Return the canonical conservative value for one supported ABI parameter."""
    defaults = conservative_defaults((parameter,))
    if defaults is None:
        raise ValueError(f"unsupported planned-call argument type: {parameter.type}")
    return defaults[parameter.name]


def render_function_arguments(experiment: Experiment, function: FunctionModel) -> tuple[str, ...]:
    """Resolve the canonical ordered ABI argument vector for an experiment.

    The planner owns the vector. An empty vector means no complete plan was safely
    produced, so the canonical conservative ABI defaults remain the explicit
    compatibility fallback.
    """
    if function.visibility not in {"public", "external"}:
        raise ValueError(f"target function is not externally callable: {function.name}")

    if experiment.target_function is not None and experiment.target_function != function.name:
        raise ValueError(
            f"experiment target mismatch: expected {experiment.target_function}, got {function.name}"
        )

    if experiment.planned_inputs:
        if len(experiment.planned_inputs) != len(function.parameters):
            raise ValueError(
                f"planned input arity mismatch for {function.name}: "
                f"expected {len(function.parameters)}, got {len(experiment.planned_inputs)}"
            )
        return experiment.planned_inputs

    defaults = conservative_defaults(function.parameters)
    if defaults is None:
        raise ValueError(
            f"unsupported planned-call argument type in {function.name}"
        )
    return tuple(defaults[parameter.name] for parameter in function.parameters)


def render_function_call(experiment: Experiment, function: FunctionModel, receiver: str = "target") -> str:
    """Render an externally callable Solidity invocation from the canonical Experiment."""
    arguments = render_function_arguments(experiment, function)
    return f"{receiver}.{function.name}({', '.join(arguments)});"
