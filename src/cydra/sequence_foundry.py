from __future__ import annotations

from pathlib import Path
import os
import re

from .models import ContractModel, Experiment, Hypothesis
from .interface_resolver import resolve_interface, resolve_named_type_source, resolve_struct_fields
from .execution_readiness import _address_role, _constructor_role_grants, caller_role
from .runtime_observation import plan_public_state_observations
from .state_relation_observation import plan_state_relation_observations


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
    return (
        '"'
        + value.replace("\\", "\\\\").replace('"', '\\"').replace("\r", "\\r").replace("\n", "\\n").replace("\t", "\\t")
        + '"'
    )


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
    arguments: tuple[str, ...],
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
            namespace, _ = base.split(".", 1)
            resolved = resolve_interface(project_root, source_path, namespace)
            return base, resolved.source_path
        resolved_source, _ = resolve_named_type_source(project_root, source_path, base)
        return base, resolved_source

    def add_import(type_name: str) -> None:
        base, resolved_source = resolve_custom_type(type_name)
        symbol = base.split(".", 1)[0] if "." in base else base
        relative = Path(os.path.relpath(Path(project_root / resolved_source), output_path.parent)).as_posix()
        imports.append(f'import {{ {symbol} }} from "{relative}";')

    def typed_tuple(type_name: str, expression: str, defining_source: str) -> str:
        parts = _split_top_level_tuple_expression(expression)
        if parts is None or type_name.strip().endswith("[]"):
            return expression
        base = type_name.strip().split()[0]
        fields = resolve_struct_fields(project_root, defining_source, base.split(".", 1)[-1])
        if not fields:
            raise ValueError(
                f"unable to resolve struct fields for prerequisite parameter type {base} "
                f"from {defining_source}"
            )
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
                        raise ValueError(
                            f"unable to resolve nested struct type {field_base} "
                            f"for {base}.{field_name} from {defining_source}: {exc}"
                        ) from exc
                add_import(field_base)
                nested_parts = _split_top_level_tuple_expression(part)
                if nested_parts is None:
                    raise ValueError(
                        f"prerequisite nested struct value for {base}.{field_name} "
                        f"must be a tuple expression"
                    )
                rendered_parts.append(typed_tuple(field_base, part, nested_source))
            else:
                rendered_parts.append(part)
        return f"{base}({', '.join(rendered_parts)})"

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
            namespace, _ = base.split(".", 1)
            if project_root is None:
                raise ValueError(f"stack-safe lowering requires a resolvable Foundry project root for {type_name}")
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
    project_root = next(
        (ancestor for ancestor in (Path(output_path).parent, *Path(output_path).parents) if (ancestor / "foundry.toml").exists()),
        None,
    )
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
        if verify_state_prerequisites and stop_before_target and function.name == hypothesis.target_function:
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
                effective_arguments,
            )
            prerequisite_imports.extend(binding_imports)
            rendered.extend(bindings)
            rendered.extend(
                f"        assertTrue({observation.expression}, {_solidity_string_literal(f'unverified prerequisite: {observation.predicate}')});"
                for observation in observations
            )
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
    inherited_interfaces = {item.name: item for item in contract_model.inherited_resolved_interfaces}
    direct_interfaces: dict[str, object] = {}
    named_type_sources: dict[str, str] = {}
    erc20_stub_needed = False
    if project_root is not None and contract_model.constructor is not None:
        for parameter in contract_model.constructor.parameters:
            base = parameter.type.strip().split()[0].rstrip("[]")
            if base in inherited_interfaces:
                direct_interfaces[base] = inherited_interfaces[base]
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
            # Zero is not a universally safe constructor default: unsigned
            # parameters are commonly used as lower bounds in expressions such
            # as `value - 1`. Use the smallest non-zero value as the generic
            # materialization default; target-derived constraints remain the
            # authority for any stricter constructor requirement.
            constructor_arguments.append("1")
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
                resolved_namespace = resolve_interface(project_root, contract_model.source, namespace)
                fields = resolve_struct_fields(project_root, resolved_namespace.source_path, type_name)
            except (FileNotFoundError, ValueError, OSError, UnicodeError):
                fields = ()
                resolved_namespace = None
            if not fields or resolved_namespace is None:
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
            relative = Path(os.path.relpath(project_root / resolved_namespace.source_path, path.parent)).as_posix()
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
             if item.name == experiment.steps[0].function),
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

    deployment_address = role_address_expression(constructor_role_caller) if constructor_role_caller else None
    deployment_prefix = f"        vm.prank({deployment_address});\n" if deployment_address else ""

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
