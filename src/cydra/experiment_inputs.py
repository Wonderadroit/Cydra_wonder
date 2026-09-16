from __future__ import annotations

from collections.abc import Iterable, Mapping

from .compiler_constraints import ConstraintEvidence
from .constraint_candidates import ParameterCandidate, select_parameter_candidates
from .models import ParameterModel


def _default_for(parameter: ParameterModel) -> str | None:
    parameter_type = parameter.type.strip()
    base = parameter_type.split()[0].rstrip("[]") if parameter_type else ""
    if parameter_type.endswith("[]"):
        if base.startswith(("uint", "int")) or base in {"address", "bool", "bytes32", "bytes"}:
            return f"new {base}[](0)"
        return None
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
    return None


def conservative_defaults(parameters: Iterable[ParameterModel]) -> dict[str, str] | None:
    """Return a complete ABI-safe default map for directly supported parameter types.

    Unknown custom structs/enums deliberately return None so callers retain their
    existing generator fallback instead of inventing an ABI value.
    """
    defaults: dict[str, str] = {}
    for parameter in parameters:
        value = _default_for(parameter)
        if value is None:
            return None
        defaults[parameter.name] = value
    return defaults


def plan_parameter_inputs(
    parameters: Iterable[ParameterModel],
    constraints: Iterable[ConstraintEvidence],
    defaults: Mapping[str, str] | None = None,
    *,
    function_name: str | None = None,
) -> tuple[str, ...]:
    """Build an ordered ABI argument vector from evidence plus safe fallback values.

    Constraint selection is bound to the requested function and parameter identity.
    The planner knows nothing about vulnerability classes, invariants, or benchmark
    names. If a complete vector cannot be represented safely, it returns an empty
    tuple and leaves the existing generator fallback authoritative.
    """
    parameter_list = tuple(parameters)
    if defaults is None:
        defaults = conservative_defaults(parameter_list)
    if defaults is None:
        return ()

    selected: tuple[ParameterCandidate, ...] = select_parameter_candidates(
        parameter_list, constraints, function_name=function_name
    )
    by_index = {candidate.parameter_index: candidate.value for candidate in selected}
    return tuple(
        by_index.get(index, defaults.get(parameter.name, ""))
        for index, parameter in enumerate(parameter_list)
    )
