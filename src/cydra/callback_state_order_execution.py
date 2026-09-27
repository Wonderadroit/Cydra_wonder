from __future__ import annotations

from pathlib import Path
import os
import re

from .models import ContractModel, Experiment, Hypothesis
from .foundry import (
    _constructor_argument,
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
from .experiment_inputs import _definition, _parameter_from_field, _split_fields, _type_source, conservative_defaults
from .namespaced_state_observation import plan_namespaced_state_observation



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

        body = _function_body(Path(contract_model.source).read_text(encoding="utf-8"), current.name)
        for match in re.finditer(r"\b([A-Za-z_]\w*)\s*\(", body):
            callee = functions.get(match.group(1))
            if callee is not None:
                visit(callee)

    try:
        visit(function)
    except (OSError, UnicodeError):
        return None

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
    return f"{type_name}({{ {', '.join(values)} }})", path


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
    callback_setup = (
        f"{parameter.type} memory {callback_input_name} = {typed};\n"
        f"        {callback_input_name}.{'.'.join(parameter_path[1:])} = abi.encode(cydraStack);"
    )
    return {
        "parameter": parameter,
        "input_name": callback_input_name,
        "setup": declaration + "\n        " + callback_setup,
        "imports": set(imports) | {(str(stack_path_name), discovered["decoded_type"]), (str(operation_path), discovered["operation_type"])} if operation_path else set(imports) | {(str(stack_path_name), discovered["decoded_type"])},
        "typed_call_args": (callback_input_name,) + tuple(target_arguments[1:]),
    }



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
    constructor_arguments = [
        _constructor_argument(parameter)
        for parameter in (contract_model.constructor.parameters if contract_model.constructor else ())
    ]
    constructor_call = (
        f"new {target_type}({', '.join(constructor_arguments)})"
        if constructor_arguments else f"new {target_type}()"
    )
    argument_text = ", ".join(arguments)
    call_data = f"abi.encodeCall(target.{function.name}, ({argument_text}))"
    pragma = contract_model.pragma or "^0.8.20"
    path = Path(output_path)
    target_import = _layout_aware_import_path(target_import, path)
    source = f'''// SPDX-License-Identifier: UNLICENSED
pragma solidity {pragma};
import {{Test}} from "forge-std/Test.sol";
import {{ {target_type} }} from "{target_import}";

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
    {target_type} internal target;
    CydraReentrantCaller internal attacker;

    function setUp() public {{
        target = {constructor_call};
        attacker = new CydraReentrantCaller(address(target));
        bytes memory callData = {call_data};
        attacker.setReentryCallData(callData);
    }}

    function testCallbackStateOrder() public {{
        attacker.invoke(abi.encodeCall(target.{function.name}, ({argument_text})));
        assertTrue(attacker.callbackObserved(), "target did not invoke the caller-controlled callback");
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

    constructor_arguments = [
        _constructor_argument(parameter)
        for parameter in (contract_model.constructor.parameters if contract_model.constructor else ())
    ]
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
        // Reentry success/failure is an observation, not a prerequisite.
        // Causal classification consumes the recorded outcome separately.
    }}
}}
'''
    if requires_proxy_initialization(Path(contract_model.source)):
        source = adapt_generated_initialization_for_proxy(source, target_type)
    return _write_test(source, path)
