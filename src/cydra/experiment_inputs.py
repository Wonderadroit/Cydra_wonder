from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
import re

from .interface_resolver import resolve_named_type_source, resolve_import, _imports_for
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
        # Bounded explicit-import fallback for temporary/source-unit layouts.
        # This remains target-graph scoped and does not perform repository-wide
        # symbol discovery.
        queue = [source_path.resolve()]
        visited: set[Path] = set()
        resolved_path = None
        while queue and resolved_path is None:
            current = queue.pop(0)
            if current in visited or not current.is_file():
                continue
            visited.add(current)
            try:
                current_source = current.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            if _definition(current_source, short_name) is not None:
                resolved_path = current
                break
            for import_path in _imports_for(current):
                imported = resolve_import(root, current, import_path)
                if imported is None and import_path.startswith(("./", "../")):
                    candidate = (current.parent / import_path).resolve()
                    if candidate.is_file():
                        imported = (candidate, "declared_import")
                if imported is not None:
                    queue.append(imported[0].resolve())
        if resolved_path is None:
            return None
    else:
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

    # Nested struct fields are not yet independently constraint-selected. Use
    # neutral zero defaults for structured values so optional/sentinel branches
    # are not forced into authenticated or side-effecting execution paths.
    # Top-level scalar parameters retain the historical defaults and can still
    # be overridden by compiler-linked constraints.
    if parameter_type == "address":
        return "address(0)"
    if parameter_type == "address payable":
        return "payable(address(0))"
    if parameter_type == "bool":
        return "false"
    if parameter_type.startswith(("uint", "int")):
        return "0"
    if parameter_type == "string":
        return '""'
    if parameter_type == "bytes":
        return 'bytes("")'
    if parameter_type.startswith("bytes") and parameter_type[5:].isdigit():
        width = int(parameter_type[5:])
        return f'{parameter_type}(0)'

    primitive = _default_for(parameter)
    if primitive is not None:
        return primitive

    base = parameter_type.split()[0].rstrip("[]")
    if base in seen:
        return None
    type_source = _type_source(contract_model, base)
    if type_source is None:
        return None
    _resolved_path, resolved_source = type_source
    definition = _definition(resolved_source, base)
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



@dataclass(frozen=True)
class MaterializationProof:
    """Evidence that one Solidity parameter can be recursively materialized."""
    parameter: str
    declared_type: str
    expression: str
    provenance: tuple[str, ...]


def materialize_parameter_with_provenance(
    parameter: ParameterModel,
    contract_model: ContractModel,
) -> MaterializationProof | None:
    """Recursively materialize one parameter and retain its source/type chain."""
    provenance: list[str] = []

    def materialize(item: ParameterModel, path: str, stack: tuple[str, ...]) -> str | None:
        parameter_type = item.type.strip()
        if not parameter_type:
            return None
        if parameter_type.endswith("[]"):
            element_type = parameter_type[:-2].strip()
            primitive = _default_for(ParameterModel(item.name, element_type))
            if primitive is not None:
                provenance.append(f"{path}:array-element:{element_type}:builtin")
                return f"new {element_type}[](0)"
            base = element_type.split()[0] if element_type else ""
            if not base or base in stack:
                return None
            source = _type_source(contract_model, base)
            if source is None:
                return None
            resolved_path, resolved_source = source
            provenance.append(f"{path}:type:{base}:{resolved_path}")
            if _definition(resolved_source, base) is None:
                return None
            return f"new {base}[](0)"

        primitive = _default_for(item)
        if primitive is not None:
            provenance.append(f"{path}:builtin:{parameter_type}")
            return primitive

        base = parameter_type.split()[0].rstrip("[]")
        if base in stack:
            return None
        source = _type_source(contract_model, base)
        if source is None:
            return None
        resolved_path, resolved_source = source
        provenance.append(f"{path}:type:{base}:{resolved_path}")
        definition = _definition(resolved_source, base)
        if definition is None:
            return None
        kind, _, body = definition
        if kind == "enum":
            if not any(part.strip() for part in body.split(",")):
                return None
            provenance.append(f"{path}:enum-default:0")
            return "0"
        if kind == "value":
            underlying = body.split()[0]
            provenance.append(f"{path}:value-type:{underlying}")
            return materialize(ParameterModel(item.name, underlying), path, stack + (base,))
        if kind != "struct":
            return None

        values: list[str] = []
        for field_text in _split_fields(body):
            field = _parameter_from_field(field_text)
            if field is None:
                return None
            field_path = f"{path}.{field.name}"
            provenance.append(f"{field_path}:field-type:{field.type}")
            value = materialize(field, field_path, stack + (base,))
            if value is None:
                return None
            values.append(value)
        provenance.append(f"{path}:struct-expression:{base}")
        return f"({', '.join(values)})"

    expression = materialize(parameter, parameter.name or "<unnamed>", ())
    if expression is None:
        return None
    return MaterializationProof(parameter.name, parameter.type, expression, tuple(provenance))


def prove_parameter_materialization(
    parameters: Iterable[ParameterModel],
    contract_model: ContractModel,
) -> tuple[MaterializationProof, ...] | None:
    """Return complete source-backed materialization evidence for all parameters."""
    proofs: list[MaterializationProof] = []
    for parameter in parameters:
        proof = materialize_parameter_with_provenance(parameter, contract_model)
        if proof is None:
            return None
        proofs.append(proof)
    return tuple(proofs)

def conservative_defaults(parameters: Iterable[ParameterModel], contract_model: ContractModel | None = None) -> dict[str, str] | None:
    """Return a complete ABI-safe default map for directly supported parameter types.

    Unknown custom structs/enums deliberately return None so callers retain their
    existing generator fallback instead of inventing an ABI value.
    """
    defaults: dict[str, str] = {}
    for parameter in parameters:
        # Preserve established ABI-safe primitive defaults. Structured
        # materialization is only the fallback for user-defined types; it must
        # not silently replace address(0xCAFE) / 1 with neutral zeroes.
        value = _default_for(parameter)
        if value is None and contract_model is not None:
            value = _structured_default(parameter, contract_model)
        if value is None:
            return None
        defaults[parameter.name] = value
    return defaults


def _parameter_accepts_expression(parameter: ParameterModel, expression: str) -> bool:
    """Best-effort type compatibility for preserving partial planner vectors."""
    value = expression.strip()
    if not value:
        return False
    base = parameter.type.strip().split()[0].rstrip("[]")
    if base == "address":
        return value.startswith(("address(", "payable(address(")) or value in {"attacker", "owner", "admin", "guardian", "riskManager", "liquidator", "factory"}
    if base == "bool":
        return value in {"true", "false"}
    if base.startswith(("uint", "int")):
        return bool(re.fullmatch(r"-?\d+", value)) or value.startswith("type(uint")
    if base == "string":
        return value.startswith('"')
    if base == "bytes" or base.startswith("bytes"):
        return value.startswith(("bytes(", "hex\"")) or value == "0"
    return value.startswith((base + "(", "abi.decode(")) or value.startswith("(")


def _planned_defaults(parameters: tuple[ParameterModel, ...], planned: tuple[str, ...]) -> dict[str, str]:
    """Bind a possibly partial vector to compatible parameter slots."""
    if not planned:
        return {}
    if len(planned) >= len(parameters):
        return {parameter.name: value for parameter, value in zip(parameters, planned) if value.strip()}
    result: dict[str, str] = {}
    used: set[int] = set()
    for value in planned:
        if not value.strip():
            continue
        compatible = next(
            (index for index, parameter in enumerate(parameters)
             if index not in used and _parameter_accepts_expression(parameter, value)),
            None,
        )
        if compatible is None:
            continue
        used.add(compatible)
        result[parameters[compatible].name] = value
    return result


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
    # Merge caller-supplied values with generic safe defaults. A partial
    # sequence vector is common: the planner may know only the causal amount,
    # while the remaining ABI slots still need deterministic materialization.
    # Missing entries must not become empty strings merely because a partial
    # defaults mapping was supplied.
    safe_defaults = conservative_defaults(parameter_list, contract_model)
    if safe_defaults is None:
        if defaults is None:
            return ()
        safe_defaults = dict(defaults)
    else:
        safe_defaults = {**safe_defaults, **(defaults or {})}

    selected: tuple[ParameterCandidate, ...] = select_parameter_candidates(
        parameter_list, constraints, function_name=function_name
    )
    by_index = {candidate.parameter_index: candidate.value for candidate in selected}
    return tuple(
        by_index.get(index, safe_defaults.get(parameter.name, ""))
        for index, parameter in enumerate(parameter_list)
    )
