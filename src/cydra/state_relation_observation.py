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
_PUBLIC_MAPPING_RE = re.compile(
    r"\bmapping\s*\([^;]+?\)\s+public\s+(?P<name>[A-Za-z_]\w*)\s*;"
)


def _split_mapping_type(text: str) -> tuple[str, tuple[str, ...]] | None:
    """Return final value type and getter key types for nested mappings."""
    text = text.strip()
    if not text.startswith("mapping"):
        return text, ()

    opening = text.find("(")
    if opening < 0:
        return None
    depth = 0
    separator = -1
    closing = -1
    for index in range(opening, len(text)):
        char = text[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                closing = index
                break
        elif char == "=" and index + 1 < len(text) and text[index + 1] == ">" and depth == 1:
            separator = index
    if separator < 0 or closing < 0:
        return None

    key_type = text[opening + 1:separator].strip()
    value_type = text[separator + 2:closing].strip()
    nested = _split_mapping_type(value_type)
    if nested is None:
        return None
    final_type, nested_keys = nested
    return final_type, (key_type, *nested_keys)


def _public_getters(source: str) -> dict[str, tuple[str, tuple[str, ...]]]:
    getters: dict[str, tuple[str, tuple[str, ...]]] = {}
    for match in _PUBLIC_SCALAR_RE.finditer(source):
        getters[match.group("name")] = (match.group("type"), ())
    for match in _PUBLIC_MAPPING_RE.finditer(source):
        declaration = match.group(0)
        mapping_text = declaration[: declaration.find("public")].strip()
        parsed = _split_mapping_type(mapping_text)
        if parsed is not None:
            getters[match.group("name")] = parsed
    return getters


def _normalize_type(type_name: str) -> str:
    type_name = type_name.strip()
    return "uint256" if type_name == "uint" else type_name


def plan_state_relation_observations(
    contract: ContractModel, function: FunctionModel
) -> tuple[StateRelationObservationPlan, ...]:
    """Bind source-backed relations to deterministic Solidity getters.

    Public scalar unsigned integers and public mappings whose indexes are direct
    function parameters are observable. Signed/non-numeric values, dynamic
    indexes, and ambiguous getter surfaces fail closed.
    """
    try:
        source = open(contract.source, encoding="utf-8").read()
    except (OSError, UnicodeError):
        return ()

    getters = _public_getters(source)
    parameters = {parameter.name: _normalize_type(parameter.type.split()[0]) for parameter in function.parameters}
    plans: list[StateRelationObservationPlan] = []

    for relation in plan_source_state_relations(contract, function):
        getter_info = getters.get(relation.state)
        if getter_info is None:
            continue
        state_type, key_types = getter_info
        if not state_type.startswith("uint"):
            continue

        if relation.rhs_expression is not None:
            rhs_type = parameters.get(relation.rhs_expression)
            if rhs_type is None or not rhs_type.startswith("uint"):
                continue

        indexes = relation.index_expressions
        if len(indexes) != len(key_types):
            if indexes:
                continue
        getter_arguments: list[str] = []
        valid = True
        for expression, key_type in zip(indexes, key_types):
            parameter_type = parameters.get(expression)
            if parameter_type is None or _normalize_type(key_type) != parameter_type:
                valid = False
                break
            getter_arguments.append(expression)
        if not valid:
            continue

        getter = f"target.{relation.state}({', '.join(getter_arguments)})"
        plans.append(
            StateRelationObservationPlan(
                state=relation.state,
                state_type=state_type,
                getter=getter,
                relation=relation,
                source=f"{contract.source}:{function.line}",
            )
        )
    return tuple(plans)
