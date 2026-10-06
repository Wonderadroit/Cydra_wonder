from __future__ import annotations

from dataclasses import dataclass
import json
import re
import subprocess
from pathlib import Path

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
    # State-backed mapping indexes are snapshotted before the target transition.
    # This prevents a transition that changes its own index state from comparing
    # different mapping keys before vs. after execution.
    index_state_types: tuple[tuple[str, str], ...] = ()
    observation_kind: str = "public_getter"


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


def _forge_storage_layout(project: Path, contract: ContractModel) -> dict:
    try:
        completed = subprocess.run((
            "forge", "inspect", contract.name, "storage-layout", "--json"),
            cwd=project, text=True, capture_output=True, check=False,
        )
        value = json.loads(completed.stdout) if completed.returncode == 0 else {}
        return value if isinstance(value, dict) else {}
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}

def _storage_observation(project: Path, contract: ContractModel, state: str,
                         indexes: tuple[str, ...], parameters: dict[str, str]):
    layout = _forge_storage_layout(project, contract)
    entries, types = layout.get("storage"), layout.get("types")
    if not isinstance(entries, list) or not isinstance(types, dict): return None
    entry = next((item for item in entries if item.get("label") == state), None)
    if not isinstance(entry, dict): return None
    type_id = str(entry.get("type", "")); mapping_keys = []
    while True:
        info = types.get(type_id, {})
        if info.get("encoding") != "mapping": break
        key_id, value_id = info.get("key"), info.get("value")
        if not key_id or not value_id: return None
        mapping_keys.append(str(types.get(str(key_id), {}).get("label", key_id)))
        type_id = str(value_id)
    if len(mapping_keys) != len(indexes): return None
    args = []
    for expr, key_label in zip(indexes, mapping_keys):
        if expr == "msg.sender":
            if "address" not in key_label: return None
            args.append(expr)
        elif expr in parameters:
            args.append(expr)
        else: return None
    slot = f"bytes32(uint256({entry.get('slot', '0')}))"
    for arg in args: slot = f"keccak256(abi.encode({arg}, {slot}))"
    value_info = types.get(type_id, {})
    label = str(value_info.get("label", ""))
    size = value_info.get("numberOfBytes")
    if value_info.get("encoding") != "inplace" or not isinstance(size, int) or not re.search(r"\b(?:u?int)(?:[0-9]+)?\b", label): return None
    offset = int(entry.get("offset", 0)); bits = size * 8
    if bits > 256: return None
    mask = "" if bits == 256 else f" & {hex((1 << bits) - 1)}"
    getter = f"(uint256(vm.load(address(target), {slot})) >> {offset * 8}){mask}"
    return getter, label
def plan_state_relation_observations(
    contract: ContractModel, function: FunctionModel, project: Path | None = None
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
        observation_kind = "public_getter"
        storage = None
        if getter_info is None or not getter_info[0].startswith(("uint", "int")):
            if project is None: continue
            storage = _storage_observation(project, contract, relation.state, relation.index_expressions, parameters)
            if storage is None: continue
            state_type, key_types = storage[1], ()
            observation_kind = "compiler_storage"
        else:
            state_type, key_types = getter_info

        if relation.rhs_expression is not None:
            rhs_type = parameters.get(relation.rhs_expression)
            if rhs_type is None or not rhs_type.startswith(("uint", "int")):
                continue

        indexes = relation.index_expressions
        if observation_kind == "compiler_storage":
            plans.append(StateRelationObservationPlan(state=relation.state, state_type=state_type, getter=storage[0], relation=relation, source=f"{contract.source}:{function.line}", observation_kind=observation_kind))
            continue
        if len(indexes) != len(key_types):
            if indexes:
                continue
        getter_arguments: list[str] = []
        index_state_types: list[tuple[str, str]] = []
        valid = True
        for expression, key_type in zip(indexes, key_types):
            normalized_key = _normalize_type(key_type)
            if expression == "msg.sender":
                if normalized_key != "address":
                    valid = False
                    break
                getter_arguments.append("msg.sender")
                continue

            parameter_type = parameters.get(expression)
            if parameter_type is not None:
                if normalized_key != parameter_type:
                    valid = False
                    break
                getter_arguments.append(expression)
                continue

            # A public unsigned-integer state variable may safely provide a
            # deterministic mapping index. The renderer reads it through the
            # target getter at runtime, so the index is not guessed.
            state_index = getters.get(expression)
            if (
                state_index is None
                or state_index[1]
                or not state_index[0].startswith("uint")
                or not normalized_key.startswith("uint")
            ):
                valid = False
                break
            getter_arguments.append(f"target.{expression}()")
            index_state_types.append((expression, state_index[0]))
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
                index_state_types=tuple(index_state_types),
            )
        )
    return tuple(plans)
