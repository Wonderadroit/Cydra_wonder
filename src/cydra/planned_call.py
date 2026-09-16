from __future__ import annotations

from .models import Experiment, FunctionModel, ParameterModel


def conservative_argument(parameter: ParameterModel) -> str:
    parameter_type = parameter.type.strip()
    base = parameter_type.split()[0].rstrip("[]") if parameter_type else ""
    if parameter_type.endswith("[]"):
        if base.startswith(("uint", "int")) or base in {"address", "bool", "bytes32", "bytes"}:
            return f"new {base}[](0)"
        raise ValueError(f"unsupported planned-call argument type: {parameter.type}")
    if parameter_type == "address payable":
        return "payable(address(0xCAFE))"
    if base == "address":
        return "address(0xCAFE)"
    if base == "bool":
        return "false"
    if base.startswith(("uint", "int")):
        return "1"
    if base == "string":
        return '"CYDRA"'
    if base == "bytes":
        return "bytes(\"\")"
    if base.startswith("bytes") and base[5:].isdigit():
        return "bytes32(0x01)" if base == "bytes32" else f"{base}(0x01)"
    raise ValueError(f"unsupported planned-call argument type: {parameter.type}")


def render_function_call(experiment: Experiment, function: FunctionModel, receiver: str = "target") -> str:
    """Render an externally callable Solidity invocation from the canonical Experiment.

    ``planned_inputs`` is authoritative when it contains a complete ordered ABI
    vector. An empty vector intentionally falls back to the existing conservative
    type renderer so unsupported/custom types do not get fabricated values.
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
        arguments = tuple(conservative_argument(parameter) for parameter in function.parameters)

    return f"{receiver}.{function.name}({', '.join(arguments)});"
