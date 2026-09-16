from __future__ import annotations

from collections.abc import Iterable, Mapping

from .compiler_constraints import ConstraintEvidence
from .constraint_candidates import ParameterCandidate, select_parameter_candidates
from .models import ParameterModel


def plan_parameter_inputs(
    parameters: Iterable[ParameterModel],
    constraints: Iterable[ConstraintEvidence],
    defaults: Mapping[str, str],
) -> tuple[str, ...]:
    """Build an ordered ABI argument vector from observed constraints plus fallback defaults.

    Compiler evidence may override only the parameter it actually constrains. Every
    other parameter retains the caller's conservative default. This function is
    intentionally unaware of vulnerability class, invariant, or function name.
    """
    parameter_list = tuple(parameters)
    selected: tuple[ParameterCandidate, ...] = select_parameter_candidates(
        parameter_list, constraints
    )
    by_index = {candidate.parameter_index: candidate.value for candidate in selected}
    return tuple(
        by_index.get(index, defaults.get(parameter.name, ""))
        for index, parameter in enumerate(parameter_list)
    )
