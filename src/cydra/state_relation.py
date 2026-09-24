from __future__ import annotations

from dataclasses import dataclass
import re

from .models import ContractModel, FunctionModel


@dataclass(frozen=True)
class StateRelation:
    """Source-backed postcondition for one simple storage transition.

    Only relations whose arithmetic is explicit in the target function source
    are emitted. Unknown RHS expressions are rejected rather than guessed.
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


def _function_body(source: str, function: FunctionModel) -> str:
    """Return only the selected function body, failing closed on ambiguity."""
    matches = list(
        re.finditer(
            r"\bfunction\s+" + re.escape(function.name) + r"\s*\(",
            source,
        )
    )
    if not matches:
        return ""

    # Prefer the function declaration closest to the modeled source line.
    lines_before = source.splitlines(keepends=True)
    line_offsets: list[int] = []
    offset = 0
    for line in lines_before:
        line_offsets.append(offset)
        offset += len(line)
    if not matches:
        return ""
    candidates = matches
    target = min(
        candidates,
        key=lambda match: abs(source.count("\n", 0, match.start()) + 1 - function.line),
    )

    opening = source.find("{", target.end())
    if opening < 0:
        return ""
    depth = 0
    for index in range(opening, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[opening + 1:index]
    return ""


def plan_source_state_relations(
    contract: ContractModel, function: FunctionModel
) -> tuple[StateRelation, ...]:
    """Extract conservative, directly testable state postconditions.

    This intentionally handles only literal additive/subtractive transitions
    inside the selected function body. Mappings, arrays, call results, dynamic
    expressions, and guessed invariants are left unresolved.
    """
    try:
        source = open(contract.source, encoding="utf-8").read()
    except (OSError, UnicodeError):
        return ()

    state_names = set(contract.state_variables) & set(function.writes)
    if not state_names:
        return ()

    body = _function_body(source, function)
    if not body:
        return ()

    relations: list[StateRelation] = []
    for pattern, operation in _PATTERNS:
        for match in pattern.finditer(body):
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
            relations.append(
                StateRelation(
                    state=state,
                    function=function.name,
                    expression=expression,
                    source=f"source:{contract.source}",
                )
            )
    return tuple(dict.fromkeys(relations))
