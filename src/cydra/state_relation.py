from __future__ import annotations

from dataclasses import dataclass
import re

from .models import ContractModel, FunctionModel


@dataclass(frozen=True)
class StateRelation:
    """Source-backed postcondition for one simple storage transition.

    Only relations whose arithmetic is explicit in the target source are emitted.
    Unknown RHS expressions are rejected rather than guessed.
    """

    state: str
    function: str
    expression: str
    source: str


_LITERAL = r"(?:0[xX][0-9a-fA-F]+|[0-9]+)"
_PATTERNS = (
    (re.compile(r"\b(?P<state>[A-Za-z_]\w*)\s*\+=\s*(?P<rhs>"+_LITERAL+r")\s*;"), "+"),
    (re.compile(r"\b(?P<state>[A-Za-z_]\w*)\s*-=\s*(?P<rhs>"+_LITERAL+r")\s*;"), "-"),
    (re.compile(r"\b(?P<state>[A-Za-z_]\w*)\s*\+\+\s*;"), "+1"),
    (re.compile(r"\b(?P<state>[A-Za-z_]\w*)\s*--\s*;"), "-1"),
)


def plan_source_state_relations(
    contract: ContractModel, function: FunctionModel
) -> tuple[StateRelation, ...]:
    """Extract conservative, directly testable state postconditions.

    This intentionally handles only literal additive/subtractive transitions.
    Mappings, arrays, call results, dynamic expressions, and guessed invariants
    are left unresolved.
    """
    try:
        source = open(contract.source, encoding="utf-8").read()
    except (OSError, UnicodeError):
        return ()

    state_names = set(contract.state_variables) & set(function.writes)
    if not state_names:
        return ()

    relations: list[StateRelation] = []
    for pattern, operation in _PATTERNS:
        for match in pattern.finditer(source):
            state = match.group("state")
            if state not in state_names:
                continue
            rhs = match.groupdict().get("rhs")
            if operation == "+1":
                expression = f"after({state}) == before({state}) + 1"
            elif operation == "-1":
                expression = f"after({state}) == before({state}) - 1"
            else:
                expression = f"after({state}) == before({state}) {operation} {rhs}"
            relations.append(StateRelation(
                state=state,
                function=function.name,
                expression=expression,
                source=f"source:{contract.source}",
            ))
    return tuple(dict.fromkeys(relations))
