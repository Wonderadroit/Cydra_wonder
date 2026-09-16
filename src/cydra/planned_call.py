from __future__ import annotations

from .experiment_inputs import conservative_defaults
from .models import Experiment, FunctionModel, ParameterModel


def conservative_argument(parameter: ParameterModel) -> str:
    """Return the canonical conservative value for one supported ABI parameter."""
    defaults = conservative_defaults((parameter,))
    if defaults is None:
        raise ValueError(f"unsupported planned-call argument type: {parameter.type}")
    return defaults[parameter.name]


def render_function_call(experiment: Experiment, function: FunctionModel, receiver: str = "target") -> str:
    """Render an externally callable Solidity invocation from the canonical Experiment.

    ``planned_inputs`` is authoritative when it contains a complete ordered ABI
    vector. An empty vector intentionally falls back to the canonical conservative
    type defaults so unsupported/custom types do not get fabricated values.
    """
    if function.visibility not in {"public", "external"}:
        raise ValueError(f"target function is not externally callable: {function.name}")

    if experiment.planned_inputs:
        if len(experiment.planned_inputs) != len(function.parameters):
            raise ValueError(
                f"planned input arity mismatch for {function.name}: "
                f"expected {len(function.parameters)}, got {len(experiment.planned_inputs)}"
            )
        arguments = experiment.planned_inputs
    else:
        defaults = conservative_defaults(function.parameters)
        if defaults is None:
            raise ValueError(
                f"unsupported planned-call argument type in {function.name}"
            )
        arguments = tuple(defaults[parameter.name] for parameter in function.parameters)

    return f"{receiver}.{function.name}({', '.join(arguments)});"
