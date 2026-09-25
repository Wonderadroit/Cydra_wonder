from __future__ import annotations

from dataclasses import dataclass
import re

from .models import ContractModel, FunctionModel


@dataclass(frozen=True)
class StateRelation:
    """Source-backed postcondition for one simple storage transition."""

    state: str
    function: str
    expression: str
    source: str
    index_expressions: tuple[str, ...] = ()
    rhs_expression: str | None = None


_LITERAL = r"(?:0[xX][0-9a-fA-F]+|[0-9]+)"
_RHS = _LITERAL + r"|[A-Za-z_]\w*"
_PATTERNS = (
    (re.compile(r"\b(?P<state>[A-Za-z_]\w*)\s*\+=\s*(?P<rhs>" + _RHS + r")\s*;"), "+"),
    (re.compile(r"\b(?P<state>[A-Za-z_]\w*)\s*-=\s*(?P<rhs>" + _RHS + r")\s*;"), "-"),
    (re.compile(r"\b(?P<state>[A-Za-z_]\w*)\s*=\s*(?P=state)\s*\+\s*(?P<rhs>" + _RHS + r")\s*;"), "+"),
    (re.compile(r"\b(?P<state>[A-Za-z_]\w*)\s*=\s*(?P=state)\s*-\s*(?P<rhs>" + _RHS + r")\s*;"), "-"),
    (re.compile(r"\b(?P<state>[A-Za-z_]\w*)\s*(?P<indexes>(?:\[[^\]]+\])+)\s*\+=\s*(?P<rhs>" + _RHS + r")\s*;"), "+"),
    (re.compile(r"\b(?P<state>[A-Za-z_]\w*)\s*(?P<indexes>(?:\[[^\]]+\])+)\s*-=\s*(?P<rhs>" + _RHS + r")\s*;"), "-"),
    (re.compile(r"\b(?P<state>[A-Za-z_]\w*)(?P<indexes>(?:\[[^\]]+\])+)\s*=\s*(?P=state)(?P=indexes)\s*\+\s*(?P<rhs>" + _RHS + r")\s*;"), "+"),
    (re.compile(r"\b(?P<state>[A-Za-z_]\w*)(?P<indexes>(?:\[[^\]]+\])+)\s*=\s*(?P=state)(?P=indexes)\s*-\s*(?P<rhs>" + _RHS + r")\s*;"), "-"),
    (re.compile(r"\b(?P<state>[A-Za-z_]\w*)\s*\+\+\s*;"), "+1"),
    (re.compile(r"\b(?P<state>[A-Za-z_]\w*)\s*--\s*;"), "-1"),
)


def _function_body(source: str, function: FunctionModel) -> str:
    """Return only the selected function body, failing closed on ambiguity."""
    matches = list(re.finditer(r"\bfunction\s+" + re.escape(function.name) + r"\s*\(", source))
    if not matches:
        return ""
    target = min(matches, key=lambda match: abs(source.count("\n", 0, match.start()) + 1 - function.line))
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


def _index_expressions(raw: str) -> tuple[str, ...] | None:
    expressions = tuple(item.strip() for item in re.findall(r"\[([^\]]+)\]", raw))
    if not expressions or any(item != "msg.sender" and not re.fullmatch(r"[A-Za-z_]\w*", item) for item in expressions):
        return None
    return expressions


def plan_source_state_relations(contract: ContractModel, function: FunctionModel) -> tuple[StateRelation, ...]:
    """Extract conservative, directly testable state postconditions."""
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
    parameter_names = {parameter.name for parameter in function.parameters}
    relations: list[StateRelation] = []
    for pattern, operation in _PATTERNS:
        for match in pattern.finditer(body):
            state = match.group("state")
            if state not in state_names:
                continue
            rhs = match.groupdict().get("rhs")
            rhs_expression = rhs if rhs and not re.fullmatch(_LITERAL, rhs) else None
            if rhs_expression is not None and rhs_expression not in parameter_names:
                continue
            raw_indexes = match.groupdict().get("indexes")
            indexes = _index_expressions(raw_indexes) if raw_indexes else ()
            if raw_indexes and indexes is None:
                continue
            subject = state + "".join(f"[{item}]" for item in indexes)
            if operation == "+1":
                expression = f"after({subject}) == before({subject}) + 1"
            elif operation == "-1":
                expression = f"after({subject}) == before({subject}) - 1"
            else:
                expression = f"after({subject}) == before({subject}) {operation} {rhs}"
            relations.append(StateRelation(state, function.name, expression, f"source:{contract.source}", tuple(indexes), rhs_expression))
    return tuple(dict.fromkeys(relations))
