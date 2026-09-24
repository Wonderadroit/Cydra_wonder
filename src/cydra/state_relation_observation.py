from __future__ import annotations

from dataclasses import dataclass
import re

from .models import ContractModel, FunctionModel
from .state_relation import StateRelation, plan_source_state_relations


@dataclass(frozen=True)
class StateRelationObservationPlan:
    """Executable before/after observation for a source-backed state relation."""

    state: str
    state_type: str
    getter: str
    relation: StateRelation
    source: str


_PUBLIC_SCALAR_RE = re.compile(
    r"\b(?P<type>(?:uint\d*|int\d*|bool|address|bytes\d*))\s+"
    r"(?P<visibility>public)\s+(?P<name>[A-Za-z_]\w*)\s*(?:=[^;]*)?;"
)


def _contract_body(source: str, contract_name: str) -> str:
    """Return only the selected contract body; never borrow getters from siblings."""
    declaration = re.search(
        r"\\b(?:contract|library|interface)\\s+" + re.escape(contract_name) + r"\\b[^{}]*\\{",
        source,
    )
    if declaration is None:
        return ""
    opening = declaration.end() - 1
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


def _public_scalar_getters(source: str, contract_name: str) -> dict[str, str]:
    body = _contract_body(source, contract_name)
    return {
        match.group("name"): match.group("type")
        for match in _PUBLIC_SCALAR_RE.finditer(body)
    }


def plan_state_relation_observations(
    contract: ContractModel, function: FunctionModel
) -> tuple[StateRelationObservationPlan, ...]:
    """Bind source-backed relations to deterministic zero-argument getters."""
    try:
        source = open(contract.source, encoding="utf-8").read()
    except (OSError, UnicodeError):
        return ()

    getters = _public_scalar_getters(source, contract.name)
    return tuple(
        StateRelationObservationPlan(
            state=relation.state,
            state_type=getters[relation.state],
            getter=f"target.{relation.state}()",
            relation=relation,
            source=f"{contract.source}:{function.line}",
        )
        for relation in plan_source_state_relations(contract, function)
        if relation.state in getters and getters[relation.state].startswith("uint")
    )
