from __future__ import annotations

from pathlib import Path
import os
import re

from .models import ContractModel, Experiment, Hypothesis
from .interface_resolver import resolve_interface, resolve_named_type_source, resolve_struct_fields, resolve_namespaced_struct_fields, resolve_import
from .execution_readiness import _address_role, _constructor_role_grants, caller_role, role_address_expression, constructible_state_setup_plan
from .runtime_observation import plan_public_state_observations
from .state_relation_observation import plan_state_relation_observations
from .experiment_inputs import _type_source


def _constructor_granted_caller(function, contract_model: ContractModel) -> str | None:
    """Return the runtime identity whose constructor call established a required role.

    This is target-derived provenance: when a constructor grants a role to msg.sender,
    the deployment caller owns that role. Reuse that fact instead of inventing a
    target-specific grant in the generated experiment.
    """
    modifier_invocations = dict(function.modifier_invocations)
    grants = _constructor_role_grants(contract_model)
    for modifier in function.modifiers:
        invocation = modifier_invocations.get(modifier, ())
        if not invocation:
            continue
        required_role = invocation[0].strip()
        if not any(
            role == required_role and account in {"msg.sender", "_msgSender()"}
            for role, account in grants
        ):
            continue
        normalized = re.sub(r"[^a-z0-9]", "", required_role.lower())
        if "defaultadminrole" in normalized or normalized == "admin":
            return "admin"
        role = _address_role(required_role)
        if role is not None:
            return {
                "owner": "owner",
                "admin": "admin",
                "guardian": "guardian",
                "risk_manager": "riskManager",
                "liquidator": "liquidator",
                "factory": "factory",
                "tranche": "tranche",
            }.get(role)
    return None


def _solidity_string_literal(value: str) -> str:
    """Encode arbitrary diagnostic text as a valid Solidity string literal."""
    sentinel = "__CYDRA_ESCAPED_NEWLINE__"
    value = value.replace("\\n", sentinel)
    encoded = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", "\\r")
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )
    return '"' + encoded.replace(sentinel, "\\n") + '"'


def _split_top_level_tuple_expression(value: str) -> tuple[str, ...] | None:
    """Split a parenthesized Solidity tuple expression without parsing its types."""
    text = value.strip()
    if len(text) < 2 or text[0] != "(" or text[-1] != ")":
        return None
    parts: list[str] = []
    start = 1
    stack: list[str] = []
    quote: str | None = None
    escaped = False
    pairs = {")": "(", "]": "[", "}": "{"}
    for index in range(1, len(text) - 1):
        char = text[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {'"', "'"}:
            quote = char
        elif char in "([{":
            stack.append(char)
        elif char in ")]}":
            if stack and stack[-1] == pairs[char]:
                stack.pop()
            else:
                return None
        elif char == "," and not stack:
            part = text[start:index].strip()
            if not part:
                return None
            parts.append(part)
            start = index + 1
    part = text[start:-1].strip()
    if not part:
        return None
    parts.append(part)
    return tuple(parts)


def _split_top_level_named_struct_literal(value: str) -> dict[str, str] | None:
    """Parse a Solidity-like named struct literal into field/value pairs."""
    text = value.strip()
    if len(text) < 2 or text[0] != "{" or text[-1] != "}":
        return None
    parts = _split_top_level_tuple_expression("(" + text[1:-1].strip() + ")")
    if parts is None:
        return None
    fields: dict[str, str] = {}
    for part in parts:
        colon = None
        stack: list[str] = []
        quote: str | None = None
        escaped = False
        pairs = {")": "(", "]": "[", "}": "{"}
        for index, char in enumerate(part):
            if quote is not None:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = None
                continue
            if char in {'"', "'"}:
                quote = char
            elif char in "([{":
                stack.append(char)
            elif char in ")]}":
                if not stack or stack[-1] != pairs[char]:
                    return None
                stack.pop()
            elif char == ":" and not stack:
                colon = index
                break
        if colon is None:
            return None
        name = part[:colon].strip()
        value_text = part[colon + 1:].strip()
        if not re.fullmatch(r"[A-Za-z_]\w*", name) or not value_text:
            return None
        fields[name] = value_text
    return fields or None


def _coerce_struct_constructor_to_tuple(expression: str, expected_type: str) -> str:
    """Normalize a typed constructor matching the expected struct type into a tuple."""
    text = expression.strip()
    if _split_top_level_tuple_expression(text) is not None:
        return text
    expected = expected_type.strip().split()[0].rstrip("[]")
    qualified = re.escape(expected)
    match = re.fullmatch(rf"(?:[A-Za-z_]\w*\.)?{qualified}\((.*)\)", text, re.DOTALL)
    if match is None:
        return text
    return "(" + match.group(1).strip() + ")"


def _is_builtin_sequence_type(parameter_type: str) -> bool:
    """Return whether a parameter type needs no user-defined type binding."""
    base = parameter_type.strip().split()[0].rstrip("[]")
    return (
        base in {"address", "bool", "string", "bytes"}
        or base.startswith(("uint", "int", "bytes"))
        or base.startswith(("fixed", "ufixed"))
    )


def _plan_prerequisite_parameter_bindings(
    project_root: Path,
    source_path: str,
    output_path: Path,
    function,
    contract_model: ContractModel,
    arguments: tuple[str, ...],
    *,
    materialize_via_abi: bool = False,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Materialize source-derived custom parameter values needed by observations."""
    if len(arguments) != len(function.parameters):
        raise ValueError(
            f"prerequisite parameter binding arity mismatch for {function.name}: "
            f"expected {len(function.parameters)}, got {len(arguments)}"
        )
    declarations: list[str] = []
    imports: list[str] = []

    def resolve_custom_type(type_name: str) -> tuple[str, str]:
        base = type_name.strip().split()[0].rstrip("[]")
        if "." in base:
            namespace, member = base.split(".", 1)
            # A namespaced type may be a struct declared inside the current
            # source unit (Target.Data), not an interface dependency.
            if resolve_struct_fields(project_root, source_path, member):
                return base, Path(source_path).resolve().relative_to(Path(project_root).resolve()).as_posix()
            # Plain user-defined structs are often declared directly in the
            # current source unit. Resolve that before walking the import graph;
            # this is essential for temporary/generated fixtures with no
            # Foundry metadata.
            if resolve_struct_fields(project_root, source_path, base):
                return base, Path(source_path).resolve().relative_to(Path(project_root).resolve()).as_posix()
            if resolve_namespaced_struct_fields(project_root, source_path, namespace, member):
                return base, Path(source_path).resolve().relative_to(Path(project_root).resolve()).as_posix()
            # Namespaced Solidity types can be nested in a contract/library as
            # well as an interface (e.g. Outer.Inner). Resolve the namespace as
            # a generic declared type; resolve_interface is intentionally limited
            # to interface ABI provenance.
            namespace_source, _ = resolve_named_type_source(project_root, source_path, namespace)
            if not resolve_namespaced_struct_fields(project_root, namespace_source, namespace, member):
                raise FileNotFoundError(f"Unable to resolve nested user-defined type {base} from {source_path}")
            return base, namespace_source
        # A plain user-defined struct may be declared directly in the current
        # source unit. Resolve that before consulting model metadata/imports.
        if resolve_struct_fields(project_root, source_path, base):
            return base, str(Path(source_path).resolve())
        # For imported types, resolve the explicit source edge directly before
        # relying on richer project metadata. This keeps temporary/generated
        # fixtures deterministic while remaining bounded to declared imports.
        try:
            from .interface_resolver import _imports_for
            importer_path = Path(source_path).resolve()
            declared_imports = list(_imports_for(importer_path))
            try:
                source_text = importer_path.read_text(encoding="utf-8")
                for match in re.finditer(r"[\'\"]([^\'\"]+\.sol)[\'\"]", source_text):
                    if match.group(1) not in declared_imports:
                        declared_imports.append(match.group(1))
            except (OSError, UnicodeError):
                pass
            # Keep a direct source-regex fallback for compact/generated fixtures.
            try:
                source_text = importer_path.read_text(encoding="utf-8")
                for match in re.finditer(
                    r"import\s+(?:\{[^}]*\}\s+from\s+|\*\s+as\s+[A-Za-z_]\w*\s+from\s+)?[\'\"]([^\'\"]+)[\'\"]\s*;",
                    source_text,
                ):
                    if match.group(1) not in declared_imports:
                        declared_imports.append(match.group(1))
            except (OSError, UnicodeError):
                pass
            pending = [(importer_path.parent / item).resolve() for item in declared_imports]
            visited: set[Path] = set()
            while pending:
                candidate = pending.pop(0)
                if candidate in visited or not candidate.is_file():
                    continue
                visited.add(candidate)
                # A declared named import is authoritative symbol provenance.
                # Likewise, a plain import whose filename matches the symbol is
                # unambiguous. Both cases remain strictly inside the target's
                # explicit import graph.
                import_source = importer_path.read_text(encoding="utf-8")
                candidate_suffix = candidate.relative_to(importer_path.parent).as_posix()
                if (
                    re.search(
                        rf"import\s*\{{[^}}]*\b{re.escape(base)}\b[^}}]*\}}\s+from\s+[\'\"](?:\./)?{re.escape(candidate_suffix)}[\'\"]",
                        import_source,
                    )
                    or candidate.stem == base
                ):
                    return base, str(candidate)
                try:
                    candidate_text = candidate.read_text(encoding="utf-8")
                except (OSError, UnicodeError):
                    candidate_text = ""
                if resolve_struct_fields(project_root, candidate, base) or re.search(
                    rf"\b(?:contract|interface|library|struct|enum|type)\s+{re.escape(base)}\b",
                    candidate_text,
                ):
                    return base, str(candidate)
                try:
                    nested_imports = list(_imports_for(candidate))
                    nested_text = candidate.read_text(encoding="utf-8")
                    for match in re.finditer(r"[\'\"]([^\'\"]+\.sol)[\'\"]", nested_text):
                        if match.group(1) not in nested_imports:
                            nested_imports.append(match.group(1))
                    for match in re.finditer(
                    r"import\s+(?:\{[^}]*\}\s+from\s+|\*\s+as\s+[A-Za-z_]\w*\s+from\s+)?[\'\"]([^\'\"]+)[\'\"]\s*;",
                        nested_text,
                    ):
                        if match.group(1) not in nested_imports:
                            nested_imports.append(match.group(1))
                except (OSError, UnicodeError):
                    nested_imports = ()
                for import_path in nested_imports:
                    direct = (candidate.parent / import_path).resolve()
                    if direct.is_file() and direct not in visited:
                        pending.append(direct)
        except (OSError, UnicodeError):
            pass
        resolved = _type_source(contract_model, base)
        if resolved is not None:
            resolved_path, _resolved_source = resolved
            return base, str(resolved_path)
        try:
            project = Path(project_root).resolve()
            resolved_source, _method = resolve_named_type_source(project, source_path, base)
            return base, str(resolved_source)
        except (FileNotFoundError, ValueError, OSError, UnicodeError):
            # Bounded fallback for minimal/generated fixtures. Traverse only
            # explicit source-declared import edges, including transitive edges;
            # never perform a repository-wide symbol search.
            try:
                from .interface_resolver import _imports_for
                initial_imports = _imports_for(Path(source_path).resolve())
            except (OSError, UnicodeError):
                initial_imports = ()
            pending = [
                (Path(source_path).parent / import_path).resolve()
                for import_path in initial_imports
            ]
            visited_imports: set[Path] = set()
            while pending:
                imported = pending.pop(0)
                if imported in visited_imports or not imported.is_file():
                    continue
                visited_imports.add(imported)
                try:
                    imported_text = imported.read_text(encoding="utf-8")
                except (OSError, UnicodeError):
                    continue
                if re.search(
                    rf"\b(?:contract|interface|library|struct|enum|type)\s+{re.escape(base)}\b",
                    imported_text,
                ):
                    return base, str(imported)
                try:
                    nested_imports = _imports_for(imported)
                except (OSError, UnicodeError):
                    nested_imports = ()
                for import_path in nested_imports:
                    pending.append((imported.parent / import_path).resolve())
            raise FileNotFoundError(f"Unable to resolve user-defined type {base} from {source_path}")

    def add_import(type_name: str) -> None:
        base, resolved_source = resolve_custom_type(type_name)
        symbol = base.split(".", 1)[0] if "." in base else base
        relative = Path(os.path.relpath(Path(project_root / resolved_source), output_path.parent)).as_posix()
        imports.append(f'import {{ {symbol} }} from "{relative}";')

    def typed_tuple(type_name: str, expression: str, defining_source: str) -> str:
        # Planned-input artifacts may carry escaped Solidity quotes through
        # JSON/fixture serialization. Normalize only the escaped quote form
        # before parsing the tuple; this preserves the intended Solidity value.
        expression = expression.replace('\\\"', '"')
        parts = _split_top_level_tuple_expression(expression)
        if type_name.strip().endswith("[]"):
            return expression
        base = type_name.strip().split()[0]
        fields = resolve_struct_fields(project_root, defining_source, base.split(".", 1)[-1])
        if not fields:
            # The parameter model may have already resolved a plain custom type
            # to its defining source (for example Dimensions.sol), while the
            # prerequisite function itself lives in an inheriting source
            # (HinkalBase.sol). Reuse that generic provenance before parsing the
            # wrong file locally.
            resolved_type = _type_source(contract_model, base.split(".", 1)[-1])
            if resolved_type is not None:
                resolved_path, _ = resolved_type
                defining_source = str(resolved_path)
                fields = resolve_struct_fields(project_root, defining_source, base.split(".", 1)[-1])
        if not fields:
            try:
                defining_text = Path(defining_source).read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                defining_text = ""
            struct_name = base.split(".", 1)[-1]
            marker = f"struct {struct_name}"
            marker_index = defining_text.find(marker)
            if marker_index >= 0:
                open_brace = defining_text.find("{", marker_index)
                close_brace = defining_text.find("}", open_brace + 1) if open_brace >= 0 else -1
                if open_brace >= 0 and close_brace > open_brace:
                    parsed: list[tuple[str, str]] = []
                    for statement in defining_text[open_brace + 1:close_brace].split(";"):
                        tokens = statement.strip().split()
                        if len(tokens) >= 2:
                            parsed.append((tokens[-1], " ".join(tokens[:-1])))
                    fields = tuple(parsed)
        if not fields:
            raise ValueError(
                f"unable to resolve struct fields for prerequisite parameter type {base} "
                f"from {defining_source}"
            )
        if parts is None:
            named_parts = _split_top_level_named_struct_literal(expression)
            if named_parts is not None:
                try:
                    parts = tuple(named_parts[field_name] for field_name, _ in fields)
                except KeyError as exc:
                    raise ValueError(
                        f"prerequisite named struct literal for {base} is missing field {exc.args[0]}"
                    ) from exc
            else:
                return expression
        if len(fields) != len(parts):
            raise ValueError(
                f"prerequisite struct tuple arity mismatch for {base}: "
                f"source defines {len(fields)} fields, planned input provides {len(parts)}"
            )
        rendered_parts: list[str] = []
        for (field_name, field_type), part in zip(fields, parts):
            field_base = field_type.strip().split()[0].rstrip("[]")
            is_custom_struct = (
                "." not in field_base
                and not _is_builtin_sequence_type(field_type)
                and not field_type.strip().endswith("[]")
            )
            if is_custom_struct:
                # A source unit may declare multiple top-level structs.
                # Prefer the current defining source when it already contains the
                # nested declaration; only traverse the import graph when the
                # declaration is genuinely external.
                if resolve_struct_fields(project_root, defining_source, field_base):
                    nested_source = defining_source
                else:
                    try:
                        nested_source, _ = resolve_named_type_source(project_root, defining_source, field_base)
                    except (FileNotFoundError, ValueError, OSError, UnicodeError) as exc:
                        # Reuse the generic source-backed type resolver before
                        # declaring a nested struct unmaterializable. This keeps
                        # prerequisite rendering consistent with the canonical
                        # parameter materializer and remains bounded to the
                        # target's resolved import/type graph.
                        resolved_nested = _type_source(contract_model, field_base)
                        if resolved_nested is None:
                            raise ValueError(
                                f"unable to resolve nested struct type {field_base} "
                                f"for {base}.{field_name} from {defining_source}: {exc}"
                            ) from exc
                        nested_source = resolved_nested[0]
                add_import(field_base)
                normalized_part = _coerce_struct_constructor_to_tuple(part, field_base)
                nested_parts = _split_top_level_tuple_expression(normalized_part)
                if nested_parts is None:
                    raise ValueError(
                        f"prerequisite nested struct value for {base}.{field_name} "
                        f"must be a tuple expression"
                    )
                rendered_parts.append(typed_tuple(field_base, normalized_part, nested_source))
            else:
                rendered_parts.append(part)
        # Materialize custom ABI structs through encode/decode rather than
        # direct struct construction. This works uniformly for calldata/memory
        # structs and nested user-defined members while preserving the planned
        # tuple values exactly.
        tuple_value = f"{base.split('.', 1)[-1]}({', '.join(rendered_parts)})"
        if materialize_via_abi:
            return f"abi.decode(abi.encode({', '.join(rendered_parts)}), ({base}))"
        return tuple_value

    for parameter, argument in zip(function.parameters, arguments):
        parameter_type = parameter.type.strip()
        if _is_builtin_sequence_type(parameter_type):
            continue
        if not any(
            re.search(rf"\b{re.escape(parameter.name)}\b", predicate)
            for predicate in (*function.state_predicates, *function.execution_predicates)
        ):
            continue
        add_import(parameter_type)
        _, resolved_source = resolve_custom_type(parameter_type)
        expression = typed_tuple(parameter_type, argument, resolved_source)
        declarations.append(
            f"        {parameter_type} memory {parameter.name} = {expression};"
        )
    return tuple(declarations), tuple(dict.fromkeys(imports))

def _normalize_local_parameter_type(parameter_type: str) -> str:
    """Normalize a modeled ABI parameter type for a local materialization."""
    return re.sub(r"\s+(?:memory|calldata|storage)\b", "", parameter_type).strip()

def _plan_stack_safe_argument_bindings(
    project_root: Path | None,
    source_path: str,
    output_path: Path,
    function,
    arguments: tuple[str, ...],
    step_index: int,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """Lower complex ABI arguments into typed locals before the target call."""
    if len(arguments) != len(function.parameters):
        raise ValueError(
            f"sequence input arity mismatch for {function.name}: "
            f"expected {len(function.parameters)}, got {len(arguments)}"
        )
    declarations: list[str] = []
    call_arguments: list[str] = []
    imports: list[str] = []

    def resolve_custom_type(type_name: str) -> tuple[str, str]:
        base = _normalize_local_parameter_type(type_name).split()[0].rstrip("[]")
        if "." in base:
            namespace, member = base.split(".", 1)
            if project_root is None:
                raise ValueError(f"stack-safe lowering requires a resolvable Foundry project root for {type_name}")
            # Namespaced user-defined types can be structs declared in the
            # current source unit (for example Target.Data), not interfaces.
            # Prefer the actual member declaration before treating the namespace
            # as an imported interface.
            if resolve_struct_fields(project_root, source_path, member):
                return base, Path(source_path).resolve().relative_to(Path(project_root).resolve()).as_posix()
            resolved = resolve_interface(project_root, source_path, namespace)
            return base, resolved.source_path
        if project_root is None:
            raise ValueError(f"stack-safe lowering requires a resolvable Foundry project root for {type_name}")
        resolved_source, _ = resolve_named_type_source(project_root, source_path, base)
        return base, resolved_source

    def add_import(type_name: str) -> None:
        base, resolved_source = resolve_custom_type(type_name)
        symbol = base.split(".", 1)[0] if "." in base else base
        relative = Path(os.path.relpath(Path(project_root / resolved_source), output_path.parent)).as_posix()
        imports.append(f'import {{ {symbol} }} from "{relative}";')

    for parameter_index, (parameter, argument) in enumerate(zip(function.parameters, arguments)):
        parameter_type = parameter.type.strip()
        normalized = _normalize_local_parameter_type(parameter_type)
        base = normalized.split()[0].rstrip("[]")
        dynamic = normalized.endswith("[]") or base in {"string", "bytes"}
        custom = not _is_builtin_sequence_type(parameter_type)
        tuple_expression = _split_top_level_tuple_expression(argument) is not None
        if not (dynamic or custom or tuple_expression):
            call_arguments.append(argument)
            continue
        if custom:
            add_import(parameter_type)
        local_name = f"cydra_arg_{step_index}_{parameter_index}"
        local_type = f"{normalized} memory" if (dynamic or custom) else normalized
        declarations.append(f"        {local_type} {local_name} = {argument};")
        call_arguments.append(local_name)
    return tuple(declarations), tuple(call_arguments), tuple(dict.fromkeys(imports))


def generate_sequence_test_from_experiment(
    hypothesis: Hypothesis,
    experiment: Experiment,
    target_import: str,
    target_type: str,
    output_path: str | Path,
    contract_model: ContractModel,
    *,
    verify_state_prerequisites: bool = False,
    stop_before_target: bool = False,
    verify_state_relations: bool = False,
    verify_state_relations_all_steps: bool = False,
) -> Path:
    """Render a structured ordered experiment into an executable Foundry test.

    This renderer knows only the generic ExperimentStep envelope. It does not
    inspect invariant IDs or vulnerability classes. A step must name an
    externally callable modeled function and provide an argument vector whose
    arity matches that function.
    """
    if experiment.hypothesis_id != hypothesis.hypothesis_id:
        raise ValueError(
            f"experiment/hypothesis mismatch: {experiment.hypothesis_id} != {hypothesis.hypothesis_id}"
        )
    if not experiment.steps:
        raise ValueError("sequence experiment has no structured steps")

    functions = {
        function.name: function
        for function in (*contract_model.functions, *contract_model.inherited_functions)
    }
    rendered: list[str] = []
    prerequisite_imports: list[str] = []
    relation_setups: list[str] = []
    relation_assertions: list[str] = []
    role_addresses = {"owner": "address(0x1001)", "admin": "address(0x1002)", "guardian": "address(0x1003)", "risk_manager": "address(0x1004)", "liquidator": "address(0x1005)", "factory": "address(0x1006)"}
    # Prefer the output tree's Foundry root, but fall back to the target
    # source tree. Generated tests are often emitted below a temporary test
    # directory while the model source sits at the project root.
    source_path = Path(contract_model.source).resolve()
    project_root = next(
        (
            ancestor for ancestor in (Path(output_path).parent, *Path(output_path).parents)
            if (ancestor / "foundry.toml").exists()
        ),
        None,
    )
    if project_root is None:
        project_root = next(
            (
                ancestor for ancestor in (source_path.parent, *source_path.parents)
                if (ancestor / "foundry.toml").exists()
            ),
            None,
        )
    # A minimal target fixture may be a valid Solidity project without a
    # foundry.toml. Once the target source is known, its directory is the
    # bounded fallback root for relative imports and type resolution.
    if project_root is None and source_path.parent.exists():
        project_root = source_path.parent
    for index, step in enumerate(experiment.steps):
        if not step.function.strip():
            raise ValueError(f"sequence step {index} has no function")
        function = functions.get(step.function)
        if function is None:
            raise ValueError(f"model has no sequence function: {step.function}")
        if function.visibility not in {"public", "external"}:
            raise ValueError(f"sequence function is not externally callable: {step.function}")
        # In prerequisite-observation mode the target is deliberately not
        # executed. Its step only identifies the observation surface, so ABI
        # argument materialization/arity must not block observation of setup
        # transitions for targets with complex or custom parameter types.
        effective_arguments = step.arguments
        if (
            not effective_arguments
            and function.name == hypothesis.target_function
            and experiment.planned_inputs
        ):
            effective_arguments = experiment.planned_inputs
        if verify_state_prerequisites and function.name == hypothesis.target_function:
            observations = plan_public_state_observations(contract_model, function)
            if not observations:
                raise ValueError(
                    "state prerequisite has no deterministic public runtime observation; "
                    "security sequence must fail closed"
                )
            if project_root is None:
                raise ValueError(
                    "prerequisite parameter binding requires a resolvable Foundry project root"
                )
            bindings, binding_imports = _plan_prerequisite_parameter_bindings(
                project_root,
                contract_model.source,
                Path(output_path),
                function,
                contract_model,
                effective_arguments,
                materialize_via_abi=bool(step.arguments),
            )
            prerequisite_imports.extend(binding_imports)
            rendered.extend(bindings)
            for observation in observations:
                expression = observation.expression.replace("\r", "").replace("\n", "\\n")
                message = _solidity_string_literal(f"unverified prerequisite: {observation.predicate}")
                rendered.append(f"        assertTrue({expression}, {message});")
            if stop_before_target:
                break
        if len(step.arguments) != len(function.parameters):
            raise ValueError(
                f"sequence input arity mismatch for {step.function}: "
                f"expected {len(function.parameters)}, got {len(step.arguments)}"
            )
        if any(not argument.strip() for argument in step.arguments):
            raise ValueError(f"sequence step {step.function} contains an empty argument")
        verify_relation_for_step = verify_state_relations and (
            verify_state_relations_all_steps or function.name == hypothesis.target_function
        )
        if verify_relation_for_step:
            # Reuse a state-backed mapping key only within this transition.
            # A later transition may legitimately advance the index state.
            relation_index_snapshots: dict[str, str] = {}
            relation_plans = plan_state_relation_observations(contract_model, function)
            if function.writes and not relation_plans:
                raise ValueError(
                    "state transition has no deterministic source-backed relation observation; "
                    "relation verification must fail closed"
                )
            parameter_bindings = {
                parameter.name: argument
                for parameter, argument in zip(function.parameters, step.arguments)
            }
            relation_role = caller_role(function)
            relation_caller = {
                "owner": "owner",
                "admin": "admin",
                "guardian": "guardian",
                "risk_manager": "riskManager",
                "liquidator": "liquidator",
                "factory": "factory",
            }.get(relation_role, "attacker") if relation_role else "attacker"
            for plan in relation_plans:
                getter = plan.getter
                for parameter_name, argument in parameter_bindings.items():
                    getter = re.sub(rf"\b{re.escape(parameter_name)}\b", argument, getter)
                getter = re.sub(r"\bmsg\.sender\b", relation_caller, getter)

                # A mapping index sourced from contract state must be frozen
                # before the transition. Otherwise a function that changes the
                # index state would make the post-state getter observe a
                # different key and could create false relation failures.
                for state_name, state_type in plan.index_state_types:
                    index_snapshot = relation_index_snapshots.get(state_name)
                    if index_snapshot is None:
                        index_snapshot = f"before_index_{state_name}"
                        relation_index_snapshots[state_name] = index_snapshot
                        relation_setups.append(
                            f"        {state_type} {index_snapshot} = target.{state_name}();"
                        )
                    getter = re.sub(
                        rf"\btarget\.{re.escape(state_name)}\(\)",
                        index_snapshot,
                        getter,
                    )

                snapshot_suffix = "_".join(
                    re.sub(r"[^A-Za-z0-9_]+", "_", item)
                    for item in plan.relation.index_expressions
                )
                snapshot_name = f"before_{plan.state}" + (f"_{snapshot_suffix}" if snapshot_suffix else "")
                relation_setups.append(
                    f"        {plan.state_type} {snapshot_name} = {getter};"
                )
                expression = plan.relation.expression
                if " + " in expression:
                    amount = expression.rsplit(" + ", 1)[1]
                    for parameter_name, argument in parameter_bindings.items():
                        amount = re.sub(rf"\b{re.escape(parameter_name)}\b", argument, amount)
                    relation_assertions.append(
                        f'        assertEq({getter}, {snapshot_name} + {amount}, '
                        f'"unverified state relation: {expression}");'
                    )
                elif " - " in expression:
                    amount = expression.rsplit(" - ", 1)[1]
                    for parameter_name, argument in parameter_bindings.items():
                        amount = re.sub(rf"\b{re.escape(parameter_name)}\b", argument, amount)
                    relation_assertions.append(
                        f'        assertEq({getter}, {snapshot_name} - {amount}, '
                        f'"unverified state relation: {expression}");'
                    )
        if verify_relation_for_step and relation_setups:
            rendered.extend(relation_setups)
            relation_setups.clear()
        argument_bindings, call_arguments, argument_imports = _plan_stack_safe_argument_bindings(
            project_root,
            contract_model.source,
            Path(output_path),
            function,
            step.arguments,
            index,
        )
        rendered.extend(argument_bindings)
        prerequisite_imports.extend(argument_imports)
        arguments = ", ".join(call_arguments)
        constructor_caller = _constructor_granted_caller(function, contract_model)
        role = caller_role(function)
        caller_bindings = {"owner": "owner", "admin": "admin", "guardian": "guardian", "risk_manager": "riskManager", "liquidator": "liquidator", "factory": "factory"}
        caller = constructor_caller or (caller_bindings.get(role, "attacker") if role else "attacker")
        rendered.append(f"        vm.prank({caller});\n        target.{step.function}({arguments});")
        if verify_relation_for_step and relation_assertions:
            rendered.extend(relation_assertions)
            relation_assertions.clear()

    pragma = contract_model.pragma or "^0.8.20"
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Constructor-aware deployment is part of the generic sequence renderer.
    # A target with a non-empty constructor must be instantiated with a
    # compiler-valid argument vector; otherwise Foundry reports an opaque
    # struct-constructor error before the actual experiment can execute.
    constructor_arguments: list[str] = []
    constructor_imports: list[str] = []
    inherited_interfaces = {
        item.name: item
        for item in contract_model.inherited_resolved_interfaces
        if item is not None and getattr(item, "name", None)
    }
    direct_interfaces: dict[str, object] = {}
    named_type_sources: dict[str, str] = {}
    erc20_stub_needed = False

    # Model-provided interface provenance is authoritative and does not require
    # filesystem resolution. This keeps constructor materialization usable for
    # generated/temporary targets where the source file itself is not present.
    if contract_model.constructor is not None:
        for parameter in contract_model.constructor.parameters:
            base = parameter.type.strip().split()[0].rstrip("[]")
            if base in inherited_interfaces:
                direct_interfaces[base] = inherited_interfaces[base]

    if project_root is not None and contract_model.constructor is not None:
        for parameter in contract_model.constructor.parameters:
            base = parameter.type.strip().split()[0].rstrip("[]")
            if base in direct_interfaces:
                continue
            elif "." not in base and base not in {"address", "bool", "string", "bytes"} and not base.startswith(("uint", "int", "bytes")):
                try:
                    direct_interfaces[base] = resolve_interface(project_root, contract_model.source, base)
                except (FileNotFoundError, ValueError, OSError, UnicodeError):
                    try:
                        source_path, _ = resolve_named_type_source(project_root, contract_model.source, base)
                        named_type_sources[base] = source_path
                    except (FileNotFoundError, ValueError, OSError, UnicodeError):
                        pass

    for parameter in (contract_model.constructor.parameters if contract_model.constructor else ()):
        parameter_type = parameter.type.strip()
        base = parameter_type.split()[0].rstrip("[]")
        if parameter_type.endswith("[]"):
            raise ValueError(f"unsupported sequence constructor array type: {parameter.type}")
        if base == "address":
            role = _address_role(parameter.name)
            constructor_arguments.append(role_addresses.get(role, "address(0)"))
        elif parameter_type == "address payable":
            constructor_arguments.append("payable(address(0))")
        elif base == "bool":
            constructor_arguments.append("false")
        elif base.startswith("uint"):
            # Preserve zero unless the constructor source proves zero would
            # immediately underflow.
            constructor_source = ""
            try:
                constructor_source = Path(contract_model.source).read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                pass
            parameter_name = parameter.name or ""
            needs_nonzero = bool(
                parameter_name
                and re.search(rf"\b{re.escape(parameter_name)}\s*-\s*1\b", constructor_source)
            )
            constructor_arguments.append("1" if needs_nonzero else "0")
        elif base.startswith("int"):
            constructor_arguments.append("0")
        elif base == "string":
            constructor_arguments.append('""')
        elif base == "bytes":
            constructor_arguments.append('bytes("")')
        elif base.startswith("bytes") and base[5:].isdigit():
            constructor_arguments.append("0")
        elif base in direct_interfaces:
            constructor_arguments.append(f"{base}(address(0))")
            resolved = direct_interfaces[base]
            constructor_imports.append(
                f'import {{ {base} }} from "{Path(os.path.relpath(project_root / resolved.source_path, path.parent)).as_posix()}";'
            )
        elif base in named_type_sources:
            if base == "ERC20":
                erc20_stub_needed = True
                constructor_arguments.append("ERC20(address(constructorAsset))")
            else:
                constructor_arguments.append(f"{base}(address(0))")
            resolved_path = Path(project_root / named_type_sources[base])
            relative = Path(os.path.relpath(resolved_path, path.parent)).as_posix()
            constructor_imports.append(f'import {{ {base} }} from "{relative}";')
        elif "." in base:
            namespace, type_name = base.split(".", 1)
            try:
                namespace_source, _ = resolve_named_type_source(project_root, contract_model.source, namespace)
                fields = resolve_struct_fields(project_root, namespace_source, type_name)
            except (FileNotFoundError, ValueError, OSError, UnicodeError):
                fields = ()
                namespace_source = None
            if not fields or namespace_source is None:
                raise ValueError(f"unsupported sequence constructor namespaced type: {parameter.type}")
            field_values: list[str] = []
            for field_name, field_type in fields:
                normalized = field_type.strip()
                field_base = normalized.split()[0].rstrip("[]")
                if normalized.endswith("[]"):
                    if field_base.startswith(("uint", "int", "bytes", "address", "bool")):
                        value = f"new {field_base}[](0)"
                    else:
                        raise ValueError(f"unsupported namespaced struct field type: {field_type}")
                elif field_base == "address":
                    value = "address(0)"
                elif normalized == "address payable":
                    value = "payable(address(0))"
                elif field_base == "bool":
                    value = "false"
                elif field_base.startswith("uint"):
                    value = "1"
                elif field_base.startswith(("int", "bytes")):
                    value = "0"
                else:
                    raise ValueError(f"unsupported namespaced struct field type: {field_type}")
                field_values.append(f"{field_name}: {value}")
            constructor_arguments.append(f"{namespace}.{type_name}({{{', '.join(field_values)}}})")
            relative = Path(os.path.relpath(project_root / namespace_source, path.parent)).as_posix()
            constructor_imports.append(f'import {{ {namespace} }} from "{relative}";')
        else:
            raise ValueError(f"unsupported sequence constructor type: {parameter.type}")

    constructor_args_text = ", ".join(constructor_arguments)
    constructor_call = f"new {target_type}({constructor_args_text})" if constructor_arguments else f"new {target_type}()"
    import_text = "\n".join(dict.fromkeys((*constructor_imports, *prerequisite_imports)))

    stub_declaration = (
        'contract CydraERC20ConstructorStub is ERC20 { constructor() ERC20("CYDRA", "CYDRA", 18) {} }\n'
        if erc20_stub_needed else ""
    )
    asset_declaration = "    ERC20 internal constructorAsset;\n" if erc20_stub_needed else ""
    asset_setup = "        constructorAsset = new CydraERC20ConstructorStub();\n" if erc20_stub_needed else ""
    constructor_role_caller = None
    if experiment.steps:
        first_function = next(
            (item for item in (*contract_model.functions, *contract_model.inherited_functions)
             if item is not None and item.name == experiment.steps[0].function),
            None,
        )
        if first_function is not None:
            constructor_role_caller = _constructor_granted_caller(first_function, contract_model)

        # State-setup planning can establish the deployment caller more
        # reliably than re-deriving the role from the writer's modifier alone.
        # Preserve the target-derived provenance chain:
        # prerequisite state -> writer -> caller role -> constructor caller.
        if constructor_role_caller is None:
            setup_actions = constructible_state_setup_plan(contract_model, first_function) if first_function is not None else ()
            constructor_role_caller = next(
                (action.caller_role for action in setup_actions if action.caller_role),
                None,
            )

    deployment_role_bindings = {
        "owner": "owner",
        "admin": "admin",
        "guardian": "guardian",
        "risk_manager": "riskManager",
        "liquidator": "liquidator",
        "factory": "factory",
        "tranche": "tranche",
    }
    deployment_caller = deployment_role_bindings.get(constructor_role_caller)
    deployment_prefix = f"        vm.prank({deployment_caller});\n" if deployment_caller else ""

    source = f'''// SPDX-License-Identifier: UNLICENSED
pragma solidity {pragma};
// Hypothesis: {hypothesis.hypothesis_id}
// Experiment: {experiment.experiment_id}
// Structured ordered steps are authoritative for this execution.
import {{Test}} from "forge-std/Test.sol";
import {{ {target_type} }} from "{target_import}";
{import_text}

{stub_declaration}contract CydraSequenceExperimentTest is Test {{
    {target_type} internal target;
    address internal attacker = address(0xBEEF);\n    address internal owner = address(0x1001);\n    address internal admin = address(0x1002);\n    address internal guardian = address(0x1003);\n    address internal riskManager = address(0x1004);\n    address internal liquidator = address(0x1005);\n    address internal factory = address(0x1006);
{asset_declaration}    function setUp() public {{
{asset_setup}{deployment_prefix}        target = {constructor_call};
    }}

    function testOrderedExperimentSequence() public {{
{chr(10).join(rendered)}
    }}
}}
'''
    path.write_text(source, encoding="utf-8")
    return path
