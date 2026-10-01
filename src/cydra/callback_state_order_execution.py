from __future__ import annotations

from pathlib import Path
import os
import re

from .models import ContractModel, Experiment, Hypothesis
from .foundry import (
    _constructor_argument,
    _runtime_stub_source,
    _initializer_argument,
    _layout_aware_import_path,
    _write_test,
    generate_initialization_test,
)
from .initialization_topology import adapt_generated_initialization_for_proxy, requires_proxy_initialization
from .caller_prerequisite import (
    _caller_bound_initializer_arguments,
    _initializer_function,
    _initializer_setup_declarations,
    _qualify_planned_target_argument,
)
from .experiment_inputs import _definition, _parameter_from_field, _split_fields, _type_source, _structured_default, conservative_defaults, qualified_user_type
from .namespaced_state_observation import plan_namespaced_state_observation
from . import execution_readiness
from .execution_readiness import constructible_state_setup_plan, runtime_dependency_constructor_bindings
from .interface_resolver import resolve_import, resolve_interface, _imports_for, _extract_interface



def _function_body(source: str, function_name: str) -> str:
    match = re.search(rf"\bfunction\s+{re.escape(function_name)}\s*\([^)]*\)[^{{;]*{{", source)
    if not match:
        return ""
    depth = 1
    for index in range(match.end(), len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[match.end():index]
    return ""


def _split_top_level_tuple_expression(expression: str) -> tuple[str, ...] | None:
    """Split a Solidity tuple literal without breaking nested arrays/tuples."""
    value = expression.strip()
    if not (value.startswith("(") and value.endswith(")")):
        return None
    inner = value[1:-1]
    parts: list[str] = []
    start = 0
    depth = 0
    quote: str | None = None
    for index, char in enumerate(inner):
        if quote is not None:
            if char == "\\":
                continue
            if char == quote:
                quote = None
            continue
        if char in {"\"", "'"}:
            quote = char
        elif char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
            if depth < 0:
                return None
        elif char == "," and depth == 0:
            parts.append(inner[start:index].strip())
            start = index + 1
    tail = inner[start:].strip()
    if tail:
        parts.append(tail)
    elif inner.strip():
        return None
    return tuple(parts)

def _execution_context_warp(contract_model: ContractModel, function) -> str | None:
    """Return a conservative Foundry time control for guarded internal predicates.

    Only a must-not-hold timestamp comparison is controllable here. The adapter
    chooses the extremal EVM timestamp that makes the guarded comparison false;
    mixed low/high requirements fail closed rather than guessing an interval.
    """
    functions = {item.name: item for item in (*contract_model.functions, *contract_model.inherited_functions)}
    visited: set[str] = set()
    modes: set[str] = set()

    def visit(current) -> None:
        if current.name in visited:
            return
        visited.add(current.name)
        for predicate, polarity in current.execution_predicate_polarities:
            if polarity != "must_not_hold":
                continue
            match = re.search(r"\bblock\.timestamp\s*(>=|>|<=|<)", predicate)
            if not match:
                continue
            modes.add("low" if match.group(1) in {">", ">="} else "high")

        try:
            source = Path(contract_model.source).read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            source = ""
        body = _function_body(source, current.name) if source else ""
        for match in re.finditer(r"\b([A-Za-z_]\w*)\s*\(", body):
            callee = functions.get(match.group(1))
            if callee is not None:
                visit(callee)

    try:
        visit(function)
    except (OSError, UnicodeError):
        return None

    if not modes:
        candidates = [item for item in functions.values() if item is not function and any(p == "must_not_hold" and "block.timestamp" in pred for pred, p in item.execution_predicate_polarities)]
        if len(candidates) == 1:
            for pred, polarity in candidates[0].execution_predicate_polarities:
                if polarity == "must_not_hold":
                    match = re.search(r"\bblock\.timestamp\s*(>=|>|<=|<)", pred)
                    if match:
                        modes.add("low" if match.group(1) in {">", ">="} else "high")

    if modes == {"low"}:
        return "vm.warp(0);"
    if modes == {"high"}:
        return "vm.warp(type(uint256).max);"
    return None

def _decoded_callback_path(contract_model: ContractModel, function_name: str):
    """Discover a decoded struct -> operation endpoint callback path from source.

    This is syntax/data-flow discovery only. It requires the target itself to show
    an abi.decode source feeding an operation endpoint external call; no target
    names are recognized here.
    """
    source = Path(contract_model.source).read_text(encoding="utf-8")
    body = _function_body(source, function_name)
    decode = re.search(
        r"\b(?P<type>[A-Za-z_]\w*)\s+memory\s+(?P<var>[A-Za-z_]\w*)\s*=\s*abi\.decode\(\s*(?P<expr>[A-Za-z_]\w*(?:\.[A-Za-z_]\w+)*)\s*,\s*\((?P<decoded>[A-Za-z_]\w*)\)\s*\)",
        body,
    )
    if not decode:
        return None
    decoded_var = decode.group("var")
    decoded_type = decode.group("decoded")
    op = re.search(
        rf"\b(?P<op_type>[A-Za-z_]\w*)\s+memory\s+(?P<op>[A-Za-z_]\w*)\s*=\s*{re.escape(decoded_var)}\.[A-Za-z_]\w*\[[^]]+\]",
        body,
    )
    if not op:
        return None
    op_var = op.group("op")
    call = re.search(
        rf"\b{re.escape(op_var)}\.(?P<endpoint>[A-Za-z_]\w*)\.call(?:\s*\{{[^}}]*\}})?\s*\(\s*(?P<data>[^,)]*)",
        body,
    )
    if not call:
        return None
    return {
        "parameter_path": decode.group("expr").split("."),
        "decoded_type": decoded_type,
        "operation_type": op.group("op_type"),
        "endpoint_field": call.group("endpoint"),
        "call_data_field": call.group("data").strip(),
    }


def _struct_fields(contract_model: ContractModel, type_name: str):
    resolved = _type_source(contract_model, type_name)
    if resolved is None:
        return None
    path, source = resolved
    definition = _definition(source, type_name)
    if definition is None or definition[0] != "struct":
        return None
    fields = []
    for field_text in _split_fields(definition[2]):
        field = _parameter_from_field(field_text)
        if field is None:
            return None
        fields.append(field)
    return path, fields


def _named_struct_literal(contract_model: ContractModel, type_name: str, overrides: dict[str, str]):
    resolved = _struct_fields(contract_model, type_name)
    if resolved is None:
        return None
    path, fields = resolved
    values = []
    defaults = conservative_defaults(fields, contract_model)
    if defaults is None:
        defaults = {}
    for field in fields:
        value = overrides.get(field.name, defaults.get(field.name))
        if value is None:
            return None
        values.append(f"{field.name}: {value}")
    qualified = qualified_user_type(contract_model, type_name)
    return f"{qualified}({{ {', '.join(values)} }})", path


def _caller_bound_parameter_paths(contract_model: ContractModel, function) -> tuple[str, ...]:
    """Discover calldata paths that the target explicitly binds to msg.sender.

    This is target-derived predicate/data-flow reasoning. The adapter does not
    name a field or contract; it only materializes an equality already expressed
    by the target's modeled execution predicates.
    """
    functions = {item.name: item for item in (*contract_model.functions, *contract_model.inherited_functions)}
    ordered: list[str] = []
    visited: set[str] = set()

    def visit(current) -> None:
        if current.name in visited:
            return
        visited.add(current.name)
        predicates = current.execution_predicates
        for predicate in predicates:
            match = re.search(
                r"\b(?P<path>[A-Za-z_]\w*(?:\.[A-Za-z_]\w+)*)\s*==\s*msg\.sender\b|"
                r"\bmsg\.sender\s*==\s*(?P<reverse>[A-Za-z_]\w*(?:\.[A-Za-z_]\w+)*)\b",
                predicate,
            )
            if not match:
                continue
            path = match.group("path") or match.group("reverse")
            if any(path.split(".", 1)[0] == parameter.name for parameter in function.parameters) and path not in ordered:
                ordered.append(path)
        try:
            body = _function_body(Path(contract_model.source).read_text(encoding="utf-8"), current.name)
        except (OSError, UnicodeError):
            return
        for call in re.finditer(r"\b([A-Za-z_]\w*)\s*\(", body):
            callee = functions.get(call.group(1))
            if callee is not None:
                visit(callee)

    if function.parameters:
        visit(function)
    return tuple(ordered)


def _callback_metadata_setup(contract_model: ContractModel, function, target_arguments: tuple[str, ...], target_type: str):
    """Return declarations/imports that bind a decoded external endpoint to attacker."""
    discovered = _decoded_callback_path(contract_model, function.name)
    if discovered is None:
        return None
    parameter_path = discovered["parameter_path"]
    parameter = next((p for p in function.parameters if p.name == parameter_path[0]), None)
    if parameter is None or len(parameter_path) < 2:
        return None

    stack_literal = _named_struct_literal(
        contract_model,
        discovered["decoded_type"],
        {},
    )
    operation_literal = _named_struct_literal(
        contract_model,
        discovered["operation_type"],
        {discovered["endpoint_field"]: "address(attacker)", "value": "0", "callData": "bytes(\"\")"},
    )
    if stack_literal is None or operation_literal is None:
        return None
    _stack_value, stack_path = stack_literal
    operation_value, operation_path = operation_literal

    stack_fields = _struct_fields(contract_model, discovered["decoded_type"])
    if stack_fields is None:
        return None
    stack_path_name, fields = stack_fields
    ops_field = next((field for field in fields if field.type.split()[0].rstrip("[]") == discovered["operation_type"] and field.type.endswith("[]")), None)
    if ops_field is None:
        return None
    stack_overrides = {ops_field.name: f"new {discovered['operation_type']}[](1)"}
    stack_with_ops = _named_struct_literal(contract_model, discovered["decoded_type"], stack_overrides)
    if stack_with_ops is None:
        return None
    stack_expr = stack_with_ops[0]
    declaration = f"{discovered['operation_type']}[] memory cydraOps = new {discovered['operation_type']}[](1);\n        cydraOps[0] = {operation_value};\n        {discovered['decoded_type']} memory cydraStack = {stack_expr};\n        cydraStack.{ops_field.name} = cydraOps;"

    metadata_field = parameter_path[-1]
    callback_input = target_arguments[0]
    typed, imports = _qualify_planned_target_argument(parameter, callback_input, target_type, contract_model)
    callback_input_name = "cydraCallbackInput"
    interface_names = {item.name for item in contract_model.inherited_resolved_interfaces}
    try:
        callback_source_text = Path(contract_model.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        callback_source_text = ""
    base_parameter_type = parameter.type.strip().split()[0]
    is_reference_interface = base_parameter_type in interface_names or bool(
        re.search(rf"\binterface\s+{re.escape(base_parameter_type)}\b", callback_source_text)
    )
    location = "" if is_reference_interface else " memory"
    callback_setup = (
        f"{_memory_parameter_type(parameter.type)}{location} {callback_input_name} = {typed};\n"
        f"        {callback_input_name}.{'.'.join(parameter_path[1:])} = abi.encode(cydraStack);"
    )
    caller_bindings = _caller_bound_parameter_paths(contract_model, function)
    if caller_bindings:
        callback_setup += "".join(
            f"\n        {callback_input_name}.{path.split('.', 1)[1]} = address(attacker);"
            for path in caller_bindings
            if path.startswith(parameter.name + ".")
        )
    stack_import_type = qualified_user_type(contract_model, discovered["decoded_type"]).split(".", 1)[0]
    operation_import_type = qualified_user_type(contract_model, discovered["operation_type"]).split(".", 1)[0]
    import_provenance = {(str(stack_path_name), stack_import_type)}
    if operation_path:
        import_provenance.add((str(operation_path), operation_import_type))
    return {
        "parameter": parameter,
        "input_name": callback_input_name,
        "setup": declaration + "\n        " + callback_setup,
        "imports": set(imports) | import_provenance,
        "typed_call_args": (callback_input_name,) + tuple(target_arguments[1:]),
    }




def _call_arguments(body: str, opening: int) -> tuple[str, ...]:
    """Split one same-contract call's arguments without parsing Solidity semantics."""
    depth = 0
    bracket = 0
    start = opening + 1
    arguments: list[str] = []
    for index in range(opening + 1, len(body)):
        char = body[index]
        if char == "(":
            depth += 1
        elif char == ")":
            if depth == 0:
                value = body[start:index].strip()
                if value:
                    arguments.append(value)
                return tuple(arguments)
            depth -= 1
        elif char == "[":
            bracket += 1
        elif char == "]":
            bracket = max(0, bracket - 1)
        elif char == "," and depth == 0 and bracket == 0:
            arguments.append(body[start:index].strip())
            start = index + 1
    return ()


def _state_relation_predicates(
    contract_model: ContractModel,
    function,
    state: str,
    *,
    max_depth: int = 6,
) -> tuple[str, ...]:
    """Propagate state predicates through the modeled same-contract call graph.

    The returned predicates remain target-derived expressions. At each internal
    call boundary, callee parameters are substituted with the actual call
    expressions observed at that boundary, so a state relation discovered in a
    helper can be rendered against the original experiment input.
    """
    functions = {
        item.name: item
        for item in (*contract_model.functions, *contract_model.inherited_functions)
    }
    source = Path(contract_model.source).read_text(encoding="utf-8")
    visited: set[tuple[str, int, tuple[tuple[str, str], ...]]] = set()
    results: list[str] = []

    def visit(current, substitutions: dict[str, str], depth: int) -> None:
        if depth > max_depth:
            return
        key = (current.name, depth, tuple(sorted(substitutions.items())))
        if key in visited:
            return
        visited.add(key)

        for predicate in current.execution_predicates:
            substituted = predicate
            for name, expression in substitutions.items():
                replacement = (
                    expression
                    if re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", expression.strip())
                    else f"({expression})"
                )
                substituted = re.sub(
                    rf"\b{re.escape(name)}\b",
                    replacement,
                    substituted,
                )
            if re.search(rf"\b{re.escape(state)}\s*\[", substituted):
                if substituted not in results:
                    results.append(substituted)

        body = _function_body(source, current.name)
        if not body:
            return
        for match in re.finditer(r"\b([A-Za-z_]\w*)\s*\(", body):
            callee = functions.get(match.group(1))
            if callee is None:
                continue
            arguments = _call_arguments(body, match.end() - 1)
            if len(arguments) != len(callee.parameters):
                continue
            child_substitutions = dict(substitutions)
            for parameter, argument in zip(callee.parameters, arguments):
                if parameter.name:
                    rendered = argument
                    for name, expression in substitutions.items():
                        replacement = (
                            expression
                            if re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", expression.strip())
                            else f"({expression})"
                        )
                        rendered = re.sub(
                            rf"\b{re.escape(name)}\b",
                            replacement,
                            rendered,
                        )
                    child_substitutions[parameter.name] = rendered
            visit(callee, child_substitutions, depth + 1)

    visit(function, {}, 0)
    return tuple(results)


def _state_setup_argument_vector(
    contract_model: ContractModel,
    consumer,
    writer,
    state: str,
    callback_input_name: str,
) -> tuple[str, ...] | None:
    """Derive writer arguments from a target-observed state relation."""
    relation = None
    for predicate in _state_relation_predicates(contract_model, consumer, state):
        match = re.search(
            rf"\b{re.escape(state)}\s*\[\s*(?P<key>[^\]]+)\s*\]\s*==\s*(?P<value>[^&|]+?)\s*(?:&&|$)",
            predicate,
        ) or re.search(
            rf"(?P<value>[^&|]+?)\s*==\s*\b{re.escape(state)}\s*\[\s*(?P<key>[^\]]+)\s*\]",
            predicate,
        )
        if match:
            relation = (match.group("key").strip(), match.group("value").strip())
            break
    if relation is None or len(writer.parameters) < 2:
        return None

    def bind(expression: str) -> str:
        bound = expression
        for parameter in consumer.parameters:
            bound = re.sub(
                rf"\b{re.escape(parameter.name)}\b",
                callback_input_name,
                bound,
            )
        return bound

    arguments = [bind(relation[0]), bind(relation[1])]
    for parameter in writer.parameters[2:]:
        rendered = _structured_default(parameter, contract_model)
        if rendered is None:
            return None
        arguments.append(rendered)
    return tuple(arguments)


def _state_setup_source(
    contract_model: ContractModel,
    consumer,
    callback_input_name: str,
) -> tuple[str, tuple[str, ...]]:
    """Render only fully constructible target-derived state setup transitions."""
    actions = constructible_state_setup_plan(contract_model, consumer)
    if not actions:
        # Bounded fallback for lightweight models: derive a mapping writer
        # directly from the consumer's target-derived internal predicate.
        functions_by_name = {
            item.name: item
            for item in (*contract_model.functions, *contract_model.inherited_functions)
        }
        for predicate in _state_relation_predicates(contract_model, consumer, next(iter(contract_model.state_variables), "")):
            match = re.search(
                r"\b([A-Za-z_]\w*)\s*\[[^\]]+\]\s*==\s*([A-Za-z_]\w*(?:\.[A-Za-z_]\w+)*)",
                predicate,
            )
            if not match:
                continue
            state_name = match.group(1)
            for writer in functions_by_name.values():
                if writer.name == consumer.name or writer.visibility not in {"public", "external"}:
                    continue
                if state_name not in writer.writes:
                    continue
                actions = (execution_readiness.SetupAction(
                    writer.name, execution_readiness.caller_role(writer), (consumer.name, state_name)
                ),)
                break
            if actions:
                break
    if not actions:
        return "", ()
    functions = {
        item.name: item
        for item in (*contract_model.functions, *contract_model.inherited_functions)
    }
    rendered: list[str] = []
    active_role: str | None = None
    for action in actions:
        writer = functions.get(action.function)
        if writer is None:
            return "", ()
        state = next((part for part in action.provenance if part in contract_model.state_variables), None)
        if state is None:
            try:
                source_text = Path(contract_model.source).read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                source_text = ""
            declared_states = set(re.findall(
                r"(?m)^\s*(?:mapping\s*\([^;{}]+\)|(?:uint|int|address|bool|bytes(?:\d+)?))\s+(?:(?:public|private|internal|external|immutable|constant)\s+)*([A-Za-z_]\w*)\s*;",
                source_text,
            ))
            state = next((part for part in action.provenance if part in declared_states), None)
        if state is None:
            return "", ()
        arguments = _state_setup_argument_vector(
            contract_model, consumer, writer, state, callback_input_name
        )
        if arguments is None:
            return "", ()
        role = action.caller_role
        if role != active_role:
            if active_role is not None:
                rendered.append("vm.stopPrank();")
            if role is not None:
                address_expr = execution_readiness.role_address_expression(role)
                if address_expr is None:
                    return "", ()
                rendered.append(f"vm.startPrank({address_expr});")
            active_role = role
        rendered.append(f"target.{writer.name}({', '.join(arguments)});")
    if active_role is not None:
        rendered.append("vm.stopPrank();")
    return "\n        ".join(rendered), tuple(action.function for action in actions)



def _memory_parameter_type(parameter_type: str) -> str:
    """Normalize a parameter type for a generated memory declaration."""
    tokens = parameter_type.strip().split()
    return tokens[0] if tokens else parameter_type.strip()


def _legacy_structured_parameter_setup(
    contract_model: ContractModel,
    function,
    arguments: tuple[str, ...],
    target_type: str,
    attacker_expression: str,
) -> tuple[str, tuple[str, ...], dict[str, str]]:
    """Materialize target-derived structured inputs needed by prerequisite setup."""
    declarations: list[str] = []
    imports: set[tuple[str, str]] = set()
    rendered_arguments: dict[str, str] = {}
    caller_bindings = _caller_bound_parameter_paths(contract_model, function)
    setup_actions = constructible_state_setup_plan(contract_model, function)
    referenced_roots = {path.split(".", 1)[0] for path in caller_bindings}
    for action in setup_actions:
        for part in action.provenance:
            for predicate in _state_relation_predicates(contract_model, function, part):
                for parameter in function.parameters:
                    if re.search(rf"\b{re.escape(parameter.name)}\b", predicate):
                        referenced_roots.add(parameter.name)
    for parameter, expression in zip(function.parameters, arguments):
        base = parameter.type.strip().split()[0].rstrip("[]")
        custom = not (
            base in {"address", "bool", "string", "bytes"}
            or base.startswith(("uint", "int", "bytes", "fixed", "ufixed"))
        )
        tuple_expression = _split_top_level_tuple_expression(expression) is not None
        # A structured tuple is itself a concrete experiment input. Materialize
        # it unconditionally before any prerequisite-specific filtering so the
        # final ABI call can never reference a dropped local identifier.
        if custom and tuple_expression:
            typed, typed_imports = _qualify_planned_target_argument(
                parameter, expression, target_type, contract_model
            )
            imports.update(typed_imports)
            resolved = _type_source(contract_model, base)
            if resolved is not None and base not in set(contract_model.declared_types):
                imports.add((str(resolved[0]), base))
            local = f"cydra_{parameter.name}"
            declarations.append(
                f"{_memory_parameter_type(parameter.type)} memory {local} = {expression.strip()};"
            )
            for path in caller_bindings:
                if path.startswith(parameter.name + "."):
                    declarations.append(
                        f"{local}.{path.split('.', 1)[1]} = {attacker_expression};"
                    )
            rendered_arguments[parameter.name] = local
            referenced_roots.add(parameter.name)
            continue
        if parameter.name not in referenced_roots:
            # Even when no prerequisite currently references this parameter,
            # the final callback renderer may select a lowered structured local
            # (for example cydra_<parameter>) for the target call. Qualify it
            # here so that any generated local is declared before abi.encodeCall.
            if parameter.type.split()[0] not in {"address", "bool", "string", "bytes"} and not parameter.type.split()[0].startswith(("uint", "int", "bytes")):
                typed, typed_imports = _qualify_planned_target_argument(
                    parameter, expression, target_type, contract_model
                )
                imports.update(typed_imports)
                if (
                    (
                        re.fullmatch(r"[A-Za-z_]\w*", typed.strip())
                        and not re.fullmatch(r"[A-Za-z_]\w*", expression.strip())
                    )
                    or expression.strip().startswith("(")
                ):
                    base = parameter.type.split()[0].rstrip("[]")
                    resolved = _type_source(contract_model, base)
                    if resolved is not None and base not in set(contract_model.declared_types):
                        imports.add((str(resolved[0]), base))
                    # Tuple-shaped structured inputs must be lowered to a stable
                    # local identifier. A qualified constructor expression is a
                    # value, not a valid declaration name.
                    local = f"cydra_{parameter.name}"
                    value = typed if re.fullmatch(r"[A-Za-z_]\w*", typed.strip()) else expression
                    declarations.append(f"{_memory_parameter_type(parameter.type)} memory {local} = {value};")
                    for path in caller_bindings:
                        if path.startswith(parameter.name + "."):
                            declarations.append(f"{local}.{path.split('.', 1)[1]} = {attacker_expression};")
                    rendered_arguments[parameter.name] = local
                    continue
            rendered_arguments[parameter.name] = expression
            continue
        typed, typed_imports = _qualify_planned_target_argument(
            parameter, expression, target_type, contract_model
        )
        imports.update(typed_imports)
        if parameter.type.split()[0] in {"address", "bool", "string", "bytes"} or parameter.type.split()[0].startswith(("uint", "int", "bytes")):
            rendered_arguments[parameter.name] = typed
            continue
        if re.fullmatch(r"[A-Za-z_]\w*", typed.strip()) and not re.fullmatch(
            r"[A-Za-z_]\w*", expression.strip()
        ):
            # Some target-derived structured expressions are lowered to a
            # generated local by the planner. If the parameter is not needed
            # for a prerequisite binding, the legacy renderer must still
            # materialize that local; otherwise the final abi.encodeCall can
            # reference an undeclared identifier.
            base = parameter.type.split()[0].rstrip("[]")
            resolved = _type_source(contract_model, base)
            if resolved is not None and base not in set(contract_model.declared_types):
                imports.add((str(resolved[0]), base))
            declarations.append(f"{parameter.type} memory {typed} = {expression};")
            rendered_arguments[parameter.name] = typed
            continue
        base = parameter.type.split()[0].rstrip("[]")
        resolved = _type_source(contract_model, base)
        if resolved is not None and base not in set(contract_model.declared_types):
            imports.add((str(resolved[0]), base))
        local = f"cydra_{parameter.name}"
        declarations.append(f"{_memory_parameter_type(parameter.type)} memory {local} = {typed};")
        for path in caller_bindings:
            if path.startswith(parameter.name + "."):
                declarations.append(
                    f"{local}.{path.split('.', 1)[1]} = {attacker_expression};"
                )
        rendered_arguments[parameter.name] = local
    return "\n        ".join(declarations), tuple(sorted(imports)), rendered_arguments


def _ensure_structured_argument_bindings(
    contract_model: ContractModel,
    function,
    arguments: tuple[str, ...],
    rendered_arguments: dict[str, str],
    target_type: str,
    existing_declarations: tuple[str, ...],
    existing_imports: set[tuple[str, str]],
) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...]]:
    """Guarantee that every generated custom argument identifier is declared before use."""
    declarations = list(existing_declarations)
    imports = set(existing_imports)
    declared = set(
        re.findall(
            r"\b(?:[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\s+memory\s+([A-Za-z_]\w*)\s*=",
            "\n".join(declarations),
        )
    )
    builtin_prefixes = ("uint", "int", "bytes", "fixed", "ufixed")
    for parameter, expression in zip(function.parameters, arguments):
        base = parameter.type.strip().split()[0].rstrip("[]")
        if base in {"address", "bool", "string", "bytes"} or base.startswith(builtin_prefixes):
            continue
        local = rendered_arguments.get(parameter.name)
        if not local or not re.fullmatch(r"[A-Za-z_]\w*", local.strip()):
            continue
        if local in declared:
            continue
        _typed, typed_imports = _qualify_planned_target_argument(
            parameter, expression, target_type, contract_model
        )
        imports.update(typed_imports)
        value = expression
        if expression.strip() == local:
            value = _structured_default(parameter, contract_model)
            if value is None:
                raise ValueError(
                    f"structured argument {parameter.name} resolved to undeclared "
                    f"identifier {local} and has no source-backed fallback"
                )
        declarations.append(f"{parameter.type} memory {local} = {value};")
        declared.add(local)
    return tuple(declarations), tuple(sorted(imports))


def _ensure_callback_argument_vector_bindings(
    contract_model: ContractModel,
    function,
    arguments: tuple[str, ...],
    argument_vector: tuple[str, ...],
    parameter_setup: str,
    imports: set[tuple[str, str]],
) -> tuple[tuple[str, ...], tuple[str, ...], set[tuple[str, str]]]:
    """Ensure final callback arguments are declared before abi.encodeCall use."""
    # parameter_setup is emitted as real newlines. Split on the actual
    # separator and use normal regex boundaries so existing declarations are
    # recognized before we add a fallback materialization.
    declarations = [item for item in parameter_setup.split("\n        ") if item.strip()]
    declared = set(re.findall(
        r"\b(?:[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\s+(?:memory|calldata|storage)\s+([A-Za-z_]\w*)\s*=",
        "\n".join(declarations),
    ))
    rendered = list(argument_vector)
    builtin_prefixes = ("uint", "int", "bytes", "fixed", "ufixed")
    for index, (parameter, expression) in enumerate(zip(function.parameters, arguments)):
        base = parameter.type.strip().split()[0].rstrip("[]")
        if base in {"address", "bool", "string", "bytes"} or base.startswith(builtin_prefixes):
            continue
        candidate = rendered[index].strip()
        if not re.fullmatch(r"[A-Za-z_]\w*", candidate) or candidate in declared:
            continue
        _typed, typed_imports = _qualify_planned_target_argument(
            parameter, expression, "", contract_model
        )
        imports.update(typed_imports)
        value = expression.strip()
        if value == candidate:
            value = _structured_default(parameter, contract_model)
            if value is None:
                raise ValueError(
                    f"callback structured argument {parameter.name} resolved to undeclared "
                    f"identifier {candidate} and has no source-backed fallback"
                )
        resolved = _type_source(contract_model, base)
        if resolved is not None and base not in set(contract_model.declared_types):
            imports.add((str(resolved[0]), base))
        interface_names = {item.name for item in contract_model.inherited_resolved_interfaces}
        try:
            source_text = Path(contract_model.source).read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            source_text = ""
        is_reference_interface = base in interface_names or bool(re.search(rf"\binterface\s+{re.escape(base)}\b", source_text))
        location = "" if is_reference_interface else " memory"
        declarations.append(f"{_memory_parameter_type(parameter.type)}{location} {candidate} = {value};")
        declared.add(candidate)
    return rendered, declarations, imports


def _select_structured_binding_name(function, rendered_arguments, parameter_setup: str) -> str:
    """Select a generated local by exact identifier, never by substring prefix."""
    for parameter in function.parameters:
        if parameter.name not in rendered_arguments:
            continue
        candidate = f"cydra_{parameter.name}"
        if re.search(rf"\b{re.escape(candidate)}\b", parameter_setup):
            return candidate
    return ""


def _legacy_callback_test(
    hypothesis: Hypothesis,
    experiment: Experiment,
    target_import: str,
    target_type: str,
    output_path: str | Path,
    contract_model: ContractModel,
) -> Path:
    function = next(
        (item for item in (*contract_model.functions, *contract_model.inherited_functions)
         if item.name == hypothesis.target_function),
        None,
    )
    if function is None:
        raise ValueError(f"model has no callback target: {hypothesis.target_function}")
    arguments = experiment.planned_inputs
    if len(arguments) != len(function.parameters):
        raise ValueError(
            f"callback input arity mismatch for {function.name}: "
            f"expected {len(function.parameters)}, got {len(arguments)}"
        )
    runtime_bindings = runtime_dependency_constructor_bindings(contract_model, function)
    # Recover state-backed interface dependencies directly from the target source
    # when lightweight models omit constructor dependency metadata. This is
    # bounded to receivers actually used by the modeled external calls.
    if contract_model.constructor is not None:
        try:
            source_text = Path(contract_model.source).read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            source_text = ""
        constructor_parameters = {p.name for p in contract_model.constructor.parameters}
        recovered_direct = []
        receivers = set()
        for call in function.external_calls:
            receiver = str(call[0]) if isinstance(call, (tuple, list)) and call else str(call).rsplit(".", 1)[0]
            if receiver:
                receivers.add(receiver)
        for receiver in receivers:
            declaration = re.search(
                rf"\b(?P<type>[A-Za-z_]\w*)\s+(?:(?:public|private|internal|external|immutable|constant)\s+)*"
                rf"{re.escape(receiver)}\s*;",
                source_text,
            )
            if declaration is None:
                continue
            assignment = re.search(
                rf"\b{re.escape(receiver)}\s*=\s*(?:{re.escape(declaration.group('type'))}\s*\(\s*)?"
                rf"(?P<parameter>[A-Za-z_]\w*)\s*\)?\s*;",
                source_text,
            )
            if assignment is None or assignment.group("parameter") not in constructor_parameters:
                continue
            try:
                resolved = resolve_interface(
                    Path(contract_model.source).resolve().parent,
                    contract_model.source,
                    declaration.group("type"),
                )
            except (FileNotFoundError, ValueError, OSError, UnicodeError):
                continue
            recovered_direct.append((assignment.group("parameter"), resolved))
        runtime_bindings = tuple(dict.fromkeys((*runtime_bindings, *recovered_direct)))
    # Accept both the historical (constructor_parameter, interface) binding
    # shape and richer provenance tuples emitted by newer readiness layers.
    # The callback renderer only needs the constructor parameter and resolved
    # interface, so normalize at this boundary instead of coupling renderers to
    # readiness metadata.
    runtime_bindings = tuple(
        (binding[0], binding[-1])
        for binding in runtime_bindings
        if len(binding) >= 2
    )
    # Last bounded fallback for minimal fixtures: recover a constructor-backed
    # interface directly from the target's declared import graph. This keeps
    # runtime stub materialization independent of richer model metadata.
    if contract_model.constructor is not None:
        source_path = Path(contract_model.source).resolve()
        try:
            source_text = source_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            source_text = ""
        constructor_parameters = {p.name for p in contract_model.constructor.parameters}
        recovered_fallback = []
        for match in re.finditer(r"[\'\"]([^\'\"]+\.sol)[\'\"]", source_text):
            import_path = match.group(1)
            direct = (source_path.parent / import_path).resolve()
            if not direct.is_file():
                continue
            try:
                imported_text = direct.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            interface_names = re.findall(r"\binterface\s+([A-Za-z_]\w*)\b", imported_text)
            for interface_name in interface_names:
                try:
                    resolved = _extract_interface(
                        interface_name, direct, "declared_import", source_path.parent
                    )
                except (OSError, UnicodeError, ValueError):
                    continue
                for parameter in contract_model.constructor.parameters:
                    if parameter.name not in constructor_parameters:
                        continue
                    if re.search(
                        rf"\b{re.escape(interface_name)}\s*\(\s*{re.escape(parameter.name)}\s*\)",
                        source_text,
                    ):
                        recovered_fallback.append((parameter.name, resolved))
        runtime_bindings = tuple(dict.fromkeys((*runtime_bindings, *recovered_fallback)))
    # Some lightweight models omit constructor/interface dependency metadata.
    # Recover only target-declared state-backed constructor bindings from the
    # source/import graph; never scan unrelated repository files.
    if contract_model.constructor is not None:
        try:
            source_text = Path(contract_model.source).read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            source_text = ""
        constructor_parameters = {p.name for p in contract_model.constructor.parameters}
        recovered = []
        for match in re.finditer(
            r"\b(?P<type>[A-Za-z_]\w*)\s+(?:(?:public|private|internal|external|immutable|constant)\s+)*"
            r"(?P<receiver>[A-Za-z_]\w*)\s*;",
            source_text,
        ):
            receiver = match.group("receiver")
            modeled_receiver = any(
                (isinstance(call, (tuple, list)) and call and str(call[0]) == receiver)
                or (not isinstance(call, (tuple, list)) and str(call).rsplit(".", 1)[0] == receiver)
                for call in function.external_calls
            )
            assignment = re.search(
                rf"\b{re.escape(receiver)}\s*=\s*(?P<type>[A-Za-z_]\w*)\s*\(\s*(?P<parameter>[A-Za-z_]\w*)\s*\)",
                source_text,
            )
            if assignment is None:
                # Direct constructor parameter assignment is the common form
                # for interface-backed state. The receiver declaration already
                # supplies the interface type, so recover the parameter without
                # requiring an explicit cast.
                direct = re.search(
                    rf"\b{re.escape(receiver)}\s*=\s*(?P<parameter>[A-Za-z_]\w*)\s*;",
                    source_text,
                )
                if direct is not None:
                    assignment = direct
                    assignment_type = match.group("type")
                else:
                    assignment_type = ""
            else:
                assignment_type = assignment.group("type")
            if assignment is None or assignment.group("parameter") not in constructor_parameters:
                continue
            try:
                resolved = resolve_interface(
                    Path(contract_model.source).resolve().parent,
                    contract_model.source,
                    assignment_type,
                )
            except (FileNotFoundError, ValueError, OSError, UnicodeError):
                continue
            if modeled_receiver or resolved.name:
                recovered.append((assignment.group("parameter"), resolved))
        runtime_bindings = tuple(dict.fromkeys((*runtime_bindings, *recovered)))
    runtime_stub_source, runtime_stub_variables = _runtime_stub_source(
        runtime_bindings, (), (), False, output_path
    )
    runtime_stub_declarations = "\n".join(
        f"    Cydra{interface.name}Stub internal {runtime_stub_variables[interface.name]};"
        for _parameter, interface in runtime_bindings
    )
    runtime_stub_setup = "\n        ".join(
        f"{runtime_stub_variables[interface.name]} = new Cydra{interface.name}Stub();"
        for _parameter, interface in runtime_bindings
    )
    runtime_constructor_arguments = {
        parameter: f"address({runtime_stub_variables[interface.name]})"
        for parameter, interface in runtime_bindings
    }
    constructor_arguments = []
    for parameter in (contract_model.constructor.parameters if contract_model.constructor else ()):
        rendered = _structured_default(parameter, contract_model)
        if parameter.name in runtime_constructor_arguments:
            rendered = runtime_constructor_arguments[parameter.name]
        elif rendered is None:
            # Preserve the existing fail-closed behavior for genuinely unresolved
            # constructor shapes; custom/namespaced structs are materialized from
            # source-backed field definitions rather than guessed ABI values.
            rendered = _constructor_argument(parameter)
        constructor_arguments.append(rendered)
    constructor_call = (
        f"new {target_type}({', '.join(constructor_arguments)})"
        if constructor_arguments else f"new {target_type}()"
    )
    parameter_setup, parameter_imports, rendered_arguments = _legacy_structured_parameter_setup(
        contract_model,
        function,
        tuple(arguments),
        target_type,
        "address(attacker)",
    )
    existing_declarations = tuple(
        item.strip()
        for item in parameter_setup.split("\n        ")
        if item.strip()
    )
    # Final ABI boundary: every custom structured argument represented by a
    # tuple or a generated identifier gets one source-backed local.
    final_declarations = list(existing_declarations)
    final_declared = set(re.findall(
        r"\b[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*\s+memory\s+([A-Za-z_]\w*)\s*=",
        "\n".join(final_declarations),
    ))
    for parameter, expression in zip(function.parameters, arguments):
        base = parameter.type.strip().split()[0].rstrip("[]")
        if base in {"address", "bool", "string", "bytes"} or base.startswith(("uint", "int", "bytes", "fixed", "ufixed")):
            continue
        candidate = rendered_arguments.get(parameter.name, f"cydra_{parameter.name}")
        if not re.fullmatch(r"[A-Za-z_]\w*", candidate.strip()) or candidate in final_declared:
            continue
        value = expression.strip()
        if re.fullmatch(r"[A-Za-z_]\w*", value):
            value = _structured_default(parameter, contract_model)
        if value is None:
            continue
        resolved = _type_source(contract_model, base)
        if resolved is not None and base not in set(contract_model.declared_types):
            parameter_imports = tuple(sorted(set(parameter_imports) | {(str(resolved[0]), base)}))
        final_declarations.append(f"{_memory_parameter_type(parameter.type)} memory {candidate} = {value};")
        final_declared.add(candidate)
    parameter_setup = "\n        ".join(final_declarations)
    declarations_tuple, imports_tuple = _ensure_structured_argument_bindings(
        contract_model,
        function,
        tuple(arguments),
        rendered_arguments,
        target_type,
        tuple(final_declarations),
        set(parameter_imports),
    )
    parameter_setup = "\n        ".join(declarations_tuple)
    parameter_imports = imports_tuple
    argument_vector = tuple(
        rendered_arguments.get(
            parameter.name,
            (
                f"cydra_{parameter.name}"
                if (
                    not (
                        parameter.type.strip().split()[0].rstrip("[]")
                        in {"address", "bool", "string", "bytes"}
                        or parameter.type.strip().split()[0].startswith(
                            ("uint", "int", "bytes", "fixed", "ufixed")
                        )
                    )
                    and _split_top_level_tuple_expression(argument) is not None
                )
                else argument
            ),
        )
        for parameter, argument in zip(function.parameters, arguments)
    )
    argument_vector, final_declarations, parameter_imports_set = _ensure_callback_argument_vector_bindings(
        contract_model,
        function,
        tuple(arguments),
        argument_vector,
        parameter_setup,
        set(parameter_imports),
    )
    parameter_setup = "\n        ".join(final_declarations)
    parameter_imports = tuple(sorted(parameter_imports_set))
    argument_text = ", ".join(argument_vector)
    call_data = f"abi.encodeCall(target.{function.name}, ({argument_text}))"
    pragma = contract_model.pragma or "^0.8.20"
    path = Path(output_path)
    target_import = _layout_aware_import_path(target_import, path)
    # State setup must consume the exact materialized callback argument used
    # by the final target call. The previous fallback re-derived a parameter
    # name and could produce a different identifier (for example cydra_c vs
    # cydra_circomData), yielding compiler errors before the experiment ran.
    callback_input_for_setup = argument_vector[0] if argument_vector else ""
    if not re.fullmatch(r"[A-Za-z_]\w*", callback_input_for_setup.strip()):
        callback_input_for_setup = ""
    state_setup, state_setup_functions = _state_setup_source(
        contract_model,
        function,
        callback_input_for_setup or _select_structured_binding_name(
            function, rendered_arguments, parameter_setup
        ),
    )
    if state_setup:
        parameter_setup = parameter_setup + ("\n        " if parameter_setup else "") + state_setup
    imports = [f'import {{ {target_type} }} from "{target_import}";']
    for import_source, type_name in parameter_imports:
        relative = Path(os.path.relpath(Path(import_source).resolve(), Path(output_path).resolve().parent)).as_posix()
        line = f'import {{ {type_name} }} from "{relative}";'
        if line not in imports:
            imports.append(line)
    source = f'''// SPDX-License-Identifier: UNLICENSED
pragma solidity {pragma};
import {{Test}} from "forge-std/Test.sol";
{chr(10).join(imports)}
{runtime_stub_source}
contract CydraReentrantCaller {{
    address internal immutable target;
    bytes internal reentryCallData;
    bool public callbackObserved;
    bool public reentrySucceeded;
    bool internal entered;

    constructor(address target_) {{ target = target_; }}
    function setReentryCallData(bytes memory data) external {{ reentryCallData = data; }}
    function invoke(bytes memory data) external {{
        (bool ok,) = target.call(data);
        require(ok, "initial target call reverted");
    }}
    fallback() external {{
        callbackObserved = true;
        if (!entered) {{
            entered = true;
            (reentrySucceeded,) = target.call(reentryCallData);
        }}
    }}
}}

contract CydraInitializationInvariantTest is Test {{
    event CydraCallbackObservation(bool callbackObserved, bool reentrySucceeded);
    {target_type} internal target;
{runtime_stub_declarations}
    CydraReentrantCaller internal attacker;

    function setUp() public {{
        {runtime_stub_setup}
        target = {constructor_call};
        {parameter_setup}
        attacker = new CydraReentrantCaller(address(target));
        bytes memory callData = {call_data};
        attacker.setReentryCallData(callData);
    }}

    function testCallbackStateOrder() public {{
        attacker.invoke(abi.encodeCall(target.{function.name}, ({argument_text})));
        assertTrue(attacker.callbackObserved(), "target did not invoke the caller-controlled callback");
        emit CydraCallbackObservation(attacker.callbackObserved(), attacker.reentrySucceeded());
        assertFalse(attacker.reentrySucceeded(), "reentrant callback succeeded");
    }}
}}
'''
    if requires_proxy_initialization(Path(contract_model.source)):
        source = adapt_generated_initialization_for_proxy(source, target_type)
    return _write_test(source, path)


def generate_callback_state_order_test(
    hypothesis: Hypothesis,
    experiment: Experiment,
    target_import: str,
    target_type: str,
    output_path: str | Path,
    contract_model: ContractModel,
) -> Path:
    """Render a generic callback experiment from target-observed call provenance."""
    function = next(
        (item for item in (*contract_model.functions, *contract_model.inherited_functions)
         if item.name == hypothesis.target_function),
        None,
    )
    if function is None:
        raise ValueError(f"model has no callback target: {hypothesis.target_function}")
    if function.visibility not in {"public", "external"}:
        raise ValueError(f"callback target is not externally callable: {function.name}")

    arguments = experiment.planned_inputs
    if len(arguments) != len(function.parameters):
        raise ValueError(
            f"callback input arity mismatch for {function.name}: "
            f"expected {len(function.parameters)}, got {len(arguments)}"
        )

    initializer = _initializer_function(contract_model)
    if initializer is None:
        return _legacy_callback_test(hypothesis, experiment, target_import, target_type, output_path, contract_model)

    path = Path(output_path)
    target_import = _layout_aware_import_path(target_import, path)

    # Reuse the canonical initialization renderer to obtain target-faithful
    # lifecycle declarations and caller-bound initializer arguments.
    synthetic = Hypothesis(
        f"{hypothesis.hypothesis_id}-CALLBACK-INIT",
        hypothesis.claim,
        "INV-INIT-001",
        initializer.name,
        hypothesis.attacker_capability,
        hypothesis.expected_impact,
    )
    lifecycle = generate_initialization_test(
        synthetic,
        target_import,
        target_type,
        path,
        contract_model=contract_model,
        experiment=Experiment(
            synthetic.hypothesis_id,
            synthetic.hypothesis_id,
            initializer.name,
            (),
            1.0,
        ),
    )
    lifecycle_source = lifecycle.read_text(encoding="utf-8")
    lifecycle_imports = [
        line.strip()
        for line in lifecycle_source.splitlines()
        if line.strip().startswith("import ") or line.strip().startswith("import{")
    ]
    initializer_args = _caller_bound_initializer_arguments(
        lifecycle_source,
        initializer.name,
        tuple(parameter.name for parameter in initializer.parameters),
    )
    setup_declarations = _initializer_setup_declarations(lifecycle_source, initializer.name)

    # The shared lifecycle renderer is the source of truth for initializer
    # arguments, but custom reference parameters can be emitted as local
    # declarations that are easy to lose when the lifecycle assertion body is
    # replaced. Recover only declarations for identifier-shaped arguments; do
    # not invent values or target-specific setup.
    declared_names: set[str] = set()
    for declaration in setup_declarations:
        declared_names.update(re.findall(r"\b([A-Za-z_]\w*)\s*;", declaration))
    recovered_declarations: list[str] = []
    for index, (parameter, argument) in enumerate(zip(initializer.parameters, initializer_args)):
        identifier = re.fullmatch(r"[A-Za-z_]\w*", argument.strip())
        if identifier is None or identifier.group(0) in declared_names:
            continue
        rendered_argument, declaration = _initializer_argument(
            parameter, target_type, index, contract_model=contract_model
        )
        if rendered_argument == argument and declaration:
            recovered_declarations.append(declaration)
            declared_names.add(identifier.group(0))
    setup_declarations.extend(recovered_declarations)

    metadata = _callback_metadata_setup(contract_model, function, arguments, target_type)
    if metadata is None:
        return _legacy_callback_test(hypothesis, experiment, target_import, target_type, output_path, contract_model)

    typed_other_args: list[str] = []
    structured_imports: set[tuple[str, str]] = set(metadata["imports"])
    for parameter, expression in zip(function.parameters[1:], arguments[1:]):
        rendered, imports = _qualify_planned_target_argument(
            parameter, expression, target_type, contract_model
        )
        typed_other_args.append(rendered)
        structured_imports.update(imports)

    target_call_arguments = ", ".join(
        [metadata["input_name"], *typed_other_args]
    )
    reentry_call = f"abi.encodeCall(target.{function.name}, ({target_call_arguments}))"

    constructor_arguments = []
    for parameter in (contract_model.constructor.parameters if contract_model.constructor else ()):
        rendered = _structured_default(parameter, contract_model)
        if rendered is None:
            rendered = _constructor_argument(parameter)
        constructor_arguments.append(rendered)
    constructor_call = (
        f"new {target_type}({', '.join(constructor_arguments)})"
        if constructor_arguments
        else f"new {target_type}()"
    )

    pragma = contract_model.pragma or "^0.8.20"
    imports = [f'import {{ {target_type} }} from "{target_import}";', *lifecycle_imports]
    output_file = path
    for import_source, type_name in sorted(structured_imports):
        relative = Path(os.path.relpath(
            Path(import_source).resolve(),
            output_file.parent.resolve(),
        )).as_posix()
        line = f'import {{ {type_name} }} from "{relative}";'
        if line not in imports:
            imports.insert(0, line)

    declarations = "".join(f"        {item}\n" for item in setup_declarations)
    setup = metadata["setup"]
    state_setup, state_setup_functions = _state_setup_source(
        contract_model, function, metadata["input_name"]
    )
    if state_setup:
        setup = setup + "\n        " + state_setup
    execution_context_warp = _execution_context_warp(contract_model, function) or ""

    # Internal callee guards may reference private ERC-7201 mapping state through
    # a storage pointer. Bind the discovered key to the generated callback input
    # and observe the state read-only before the target call. Unsupported storage
    # layouts fail closed in the planner and therefore never become assertions.
    state_observation_assertions: list[str] = []
    for predicate in function.execution_predicates:
        plan = plan_namespaced_state_observation(contract_model, function, predicate)
        if plan is None:
            continue
        bound_key = plan.key_expression
        if function.parameters:
            bound_key = re.sub(
                rf"\b{re.escape(function.parameters[0].name)}\b",
                metadata["input_name"],
                bound_key,
            )
        state_observation_assertions.append(plan.assertion_for(bound_key))
    # Internal prerequisites are modeled on their callees. Discover those
    # callees from the same source call graph used by readiness; never name a
    # target-specific function in the adapter.
    try:
        callback_source = Path(contract_model.source).read_text(encoding="utf-8")
        callback_body = _function_body(callback_source, function.name)
    except (OSError, UnicodeError):
        callback_body = ""
    modeled_functions = {
        item.name: item
        for item in (*contract_model.functions, *contract_model.inherited_functions)
    }
    seen_callees: set[str] = set()
    for call_match in re.finditer(r"\b([A-Za-z_]\w*)\s*\(", callback_body):
        callee = modeled_functions.get(call_match.group(1))
        if callee is None or callee.name in seen_callees:
            continue
        seen_callees.add(callee.name)
        for predicate in callee.execution_predicates:
            plan = plan_namespaced_state_observation(contract_model, callee, predicate)
            if plan is None:
                continue
            bound_key = plan.key_expression
            for parameter in function.parameters:
                bound_key = re.sub(
                    rf"\b{re.escape(parameter.name)}\b",
                    metadata["input_name"],
                    bound_key,
                )
            state_observation_assertions.append(plan.assertion_for(bound_key))


    source = f'''// SPDX-License-Identifier: UNLICENSED
pragma solidity {pragma};
// Hypothesis: {hypothesis.hypothesis_id}
// Experiment: {experiment.experiment_id}
// Generic callback-order experiment. The callback endpoint and payload are
// derived from target source data-flow; no target-specific function is named.
import {{Test}} from "forge-std/Test.sol";
{chr(10).join(imports)}

library CydraCallerSet {{
    function one(address caller) internal pure returns (address[] memory callers) {{
        callers = new address[](1);
        callers[0] = caller;
    }}
}}

contract CydraReentrantCaller {{
    address internal immutable target;
    bytes internal initialCallData;
    bytes internal reentryCallData;
    bool public callbackObserved;
    bool public reentrySucceeded;
    bool internal entered;

    constructor(address target_) {{
        target = target_;
    }}

    function setReentryCallData(bytes memory data) external {{
        reentryCallData = data;
    }}

    function invoke(bytes memory data) external {{
        initialCallData = data;
        (bool ok,) = target.call(initialCallData);
        require(ok, "initial target call reverted");
    }}

    fallback() external {{
        callbackObserved = true;
        if (!entered) {{
            entered = true;
            (reentrySucceeded,) = target.call(reentryCallData);
        }}
    }}
}}

contract CydraInitializationInvariantTest is Test {{
    event CydraCallbackObservation(bool callbackObserved, bool reentrySucceeded);
    {target_type} internal target;
    CydraReentrantCaller internal attacker;
    bytes internal testCallData;

    function setUp() public {{
        target = {constructor_call};
        attacker = new CydraReentrantCaller(address(target));
        address cydraAttacker = address(attacker);
        {declarations}{setup}
        target.{initializer.name}({', '.join(initializer_args)});
        {execution_context_warp}
        {chr(10).join(state_observation_assertions)}
        bytes memory reentryCallData = {reentry_call};
        attacker.setReentryCallData(reentryCallData);
        testCallData = reentryCallData;
    }}

    function testCallbackStateOrder() public {{
        attacker.invoke(testCallData);
        assertTrue(
            attacker.callbackObserved(),
            "target did not invoke the caller-controlled callback"
        );
        emit CydraCallbackObservation(attacker.callbackObserved(), attacker.reentrySucceeded());
        assertFalse(attacker.reentrySucceeded(), "reentrant callback succeeded");
    }}
}}
'''
    if requires_proxy_initialization(Path(contract_model.source)):
        source = adapt_generated_initialization_for_proxy(source, target_type)
    return _write_test(source, path)
