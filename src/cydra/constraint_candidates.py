from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from .compiler_constraints import ConstraintEvidence
from .models import ParameterModel


@dataclass(frozen=True)
class ParameterCandidate:
    parameter: str
    parameter_index: int
    value: str
    reason: str
    constraint_sources: tuple[str, ...] = ()


_NONZERO_ADDRESS = "address(0xCAFE)"


def _base_type(parameter: ParameterModel) -> str:
    return parameter.type.strip().split()[0].rstrip("[]")


def _is_address(parameter: ParameterModel) -> bool:
    return _base_type(parameter) == "address"


def _is_integer(parameter: ParameterModel) -> bool:
    return _base_type(parameter).startswith(("uint", "int"))


def _constraint_value(predicate: str, parameter: ParameterModel) -> str | None:
    name = re.escape(parameter.name)
    if _is_address(parameter):
        if re.search(rf"\b{name}\s*!=\s*(?:address\s*\(\s*)?0(?:\s*\))?", predicate):
            return _NONZERO_ADDRESS
        if re.search(rf"(?:address\s*\(\s*)?0(?:\s*\))?\s*!=\s*\b{name}\b", predicate):
            return _NONZERO_ADDRESS
        return None

    if _is_integer(parameter):
        if re.search(rf"\b{name}\s*>\s*0\b", predicate):
            return "1"
        if re.search(rf"\b{name}\s*>=\s*1\b", predicate):
            return "1"
        if re.search(rf"\b{name}\s*==\s*0\b", predicate):
            return "0"
        if re.search(rf"\b{name}\s*>=\s*0\b", predicate):
            # 1 also satisfies >= 0 and is compatible with a stricter > 0 guard.
            return "1"
    return None


def select_parameter_candidates(
    parameters: Iterable[ParameterModel],
    constraints: Iterable[ConstraintEvidence],
    *,
    function_name: str | None = None,
) -> tuple[ParameterCandidate, ...]:
    """Select conservative ABI values from compiler-linked predicates.

    Candidate selection is bound to both the target function and parameter identity
    when a function name is supplied. The selector is otherwise unaware of
    vulnerability class, invariant, or benchmark-specific function names.

    If supported constraints for one parameter imply incompatible concrete values,
    no candidate is emitted for that parameter. This fails closed instead of letting
    source ordering decide which contradictory predicate wins.
    """
    by_key: dict[tuple[str, int], list[ConstraintEvidence]] = {}
    for constraint in constraints:
        if function_name is not None and constraint.function != function_name:
            continue
        by_key.setdefault((constraint.parameter, constraint.parameter_index), []).append(constraint)

    selected: list[ParameterCandidate] = []
    for index, parameter in enumerate(parameters):
        matches = by_key.get((parameter.name, index), [])
        candidates = [
            (constraint, _constraint_value(constraint.predicate, parameter))
            for constraint in matches
        ]
        supported = [(constraint, value) for constraint, value in candidates if value is not None]
        values = {value for _, value in supported}
        if len(values) > 1:
            continue
        if not supported:
            continue

        constraint, value = supported[0]
        selected.append(
            ParameterCandidate(
                parameter=parameter.name,
                parameter_index=index,
                value=value,
                reason="satisfies observed compiler-linked predicate",
                constraint_sources=tuple(item.source for item, _ in supported),
            )
        )
    return tuple(selected)
