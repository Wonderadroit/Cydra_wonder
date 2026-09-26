from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
import re

from .interface_resolver import resolve_named_type_source
from .models import ContractModel

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
        width = int(base[5:])
        return f'{base}(hex"{("01" + "00" * (width - 1))}")'
    return None



def _balanced_body(source: str, opening: int) -> str | None:
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[opening + 1:index]
    return None


def _split_fields(body: str) -> tuple[str, ...]:
    fields: list[str] = []
    start = 0
    depth = 0
    for index, char in enumerate(body):
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth = max(0, depth - 1)
        elif char == ";" and depth == 0:
            item = body[start:index].strip()
            if item:
                fields.append(item)
            start = index + 1
    return tuple(fields)


def _definition(source: str, type_name: str) -> tuple[str, str, str] | None:
    short_name = type_name.split(".")[-1].strip()
    struct_match = re.search(rf"\bstruct\s+{re.escape(short_name)}\s*" + r"\{", source)
    if struct_match:
        body = _balanced_body(source, struct_match.end() - 1)
        if body is not None:
            return ("struct", short_name, body)
    enum_match = re.search(rf"\benum\s+{re.escape(short_name)}\s*\{{([^}}]*)\}}", source)
    if enum_match:
        return ("enum", short_name, enum_match.group(1))
    value_match = re.search(rf"\btype\s+{re.escape(short_name)}\s+is\s+([^;]+);", source)
    if value_match:
        return ("value", short_name, value_match.group(1).strip())
    return None


def _project_root(source: Path) -> Path:
    resolved = source.resolve()
    for parent in (resolved.parent, *resolved.parents):
        if any((parent / marker).exists() for marker in ("foundry.toml", "remappings.txt", "package.json", ".git")):
            return parent
    return resolved.parent


def _type_source(contract_model: ContractModel, type_name: str) -> tuple[Path, str] | None:
    source_path = Path(contract_model.source)
    try:
        source = source_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        source = ""
    if _definition(source, type_name) is not None:
        return source_path, source

    root = _project_root(source_path)
    short_name = type_name.split(".")[-1].strip()
    try:
        resolved, _ = resolve_named_type_source(root, source_path, short_name)
    except (FileNotFoundError, ValueError):
        return None
    resolved_path = (root / resolved).resolve()
    try:
        resolved_source = resolved_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    if _definition(resolved_source, short_name) is None:
        return None
    return resolved_path, resolved_source


def _parameter_from_field(field: str) -> ParameterModel | None:
    tokens = [token for token in field.split() if token not in {"memory", "calldata", "storage"}]
    if len(tokens) < 2:
        return None
    return ParameterModel(name=tokens[-1], type=" ".join(tokens[:-1]))


def _structured_default(
    parameter: ParameterModel,
    contract_model: ContractModel,
    seen: tuple[str, ...] = (),
) -> str | None:
    parameter_type = parameter.type.strip()
    if not parameter_type:
        return None

    if parameter_type.endswith("[]"):
        element = ParameterModel(name=parameter.name, type=parameter_type[:-2].strip())
        primitive = _default_for(element)
        if primitive is not None:
            return f"new {element.type}[](0)"
        base = element.type.split()[0] if element.type else ""
        if not base or base in seen or _type_source(contract_model, base) is None:
            return None
        return f"new {base}[](0)"

    primitive = _default_for(parameter)
    if primitive is not None:
        return primitive

    base = parameter_type.split()[0].rstrip("[]")
    if base in seen:
        return None
    definition = _type_source(contract_model, base)
    if definition is None:
        return None

    kind, _name, body = definition
    if kind == "enum":
        return "0" if any(item.strip() for item in body.split(",")) else None
    if kind == "value":
        return _structured_default(
            ParameterModel(name=parameter.name, type=body.split()[0]),
            contract_model,
            seen + (base,),
        )
    if kind != "struct":
        return None

    values: list[str] = []
    for field_text in _split_fields(body):
        field = _parameter_from_field(field_text)
        if field is None:
            return None
        value = _structured_default(field, contract_model, seen + (base,))
        if value is None:
            return None
        values.append(value)
    return f"({', '.join(values)})"


def conservative_defaults(parameters: Iterable[ParameterModel], contract_model: ContractModel | None = None) -> dict[str, str] | None:
    """Return a complete ABI-safe default map for directly supported parameter types.

    Unknown custom structs/enums deliberately return None so callers retain their
    existing generator fallback instead of inventing an ABI value.
    """
    defaults: dict[str, str] = {}
    for parameter in parameters:
        value = _structured_default(parameter, contract_model) if contract_model is not None else _default_for(parameter)
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
    contract_model: ContractModel | None = None,
) -> tuple[str, ...]:
    """Build an ordered ABI argument vector from evidence plus safe fallback values.

    Constraint selection is bound to the requested function and parameter identity.
    The planner knows nothing about vulnerability classes, invariants, or benchmark
    names. If a complete vector cannot be represented safely, it returns an empty
    tuple and leaves the existing generator fallback authoritative.
    """
    parameter_list = tuple(parameters)
    if defaults is None:
        defaults = conservative_defaults(parameter_list, contract_model)
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
