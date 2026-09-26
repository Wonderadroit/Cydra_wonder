from __future__ import annotations

from pathlib import Path
import re

from .models import ContractModel, Experiment, Hypothesis
from .foundry import _constructor_argument, _layout_aware_import_path, _write_test, generate_initialization_test
from .caller_prerequisite import (
    _caller_bound_initializer_arguments,
    _initializer_function,
    _initializer_setup_declarations,
    _qualify_planned_target_argument,
)
from .experiment_inputs import _definition, _parameter_from_field, _split_fields, _type_source, conservative_defaults



def _function_body(source: str, function_name: str) -> str:
    match = re.search(rf"\\bfunction\\s+{re.escape(function_name)}\\s*\\([^)]*\\)[^{{;]*{{", source)
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


def _decoded_callback_path(contract_model: ContractModel, function_name: str):
    """Discover a decoded struct -> operation endpoint callback path from source.

    This is syntax/data-flow discovery only. It requires the target itself to show
    an abi.decode source feeding an operation endpoint external call; no target
    names are recognized here.
    """
    source = Path(contract_model.source).read_text(encoding="utf-8")
    body = _function_body(source, function_name)
    decode = re.search(
        r"\\b(?P<type>[A-Za-z_]\\w*)\\s+memory\\s+(?P<var>[A-Za-z_]\\w*)\\s*=\\s*abi\\.decode\\(\\s*(?P<expr>[A-Za-z_]\\w*(?:\\.[A-Za-z_]\\w+)*)\\s*,\\s*\\((?P<decoded>[A-Za-z_]\\w*)\\)\\s*\\)",
        body,
    )
    if not decode:
        return None
    decoded_var = decode.group("var")
    decoded_type = decode.group("decoded")
    op = re.search(
        rf"\\b(?P<op_type>[A-Za-z_]\\w*)\\s+memory\\s+(?P<op>[A-Za-z_]\\w*)\\s*=\\s*{re.escape(decoded_var)}\\.[A-Za-z_]\\w*\\[[^]]+\\]",
        body,
    )
    if not op:
        return None
    op_var = op.group("op")
    call = re.search(
        rf"\\b{re.escape(op_var)}\\.(?P<endpoint>[A-Za-z_]\\w*)\\.call(?:\\s*\\{{[^}}]*\\}})?\\s*\\(\\s*(?P<data>[^,)]*)",
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
        {discovered["endpoint_field"]: "address(attacker)", "callData": "bytes(\"\")"},
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
    declaration = f"{discovered['operation_type']}[] memory cydraOps = new {discovered['operation_type']}[](1);\\n        cydraOps[0] = {operation_value};\\n        {discovered['decoded_type']} memory cydraStack = {stack_expr};\\n        cydraStack.{ops_field.name} = cydraOps;"

    metadata_field = parameter_path[-1]
    callback_input = target_arguments[0]
    typed, imports = _qualify_planned_target_argument(parameter, callback_input, target_type, contract_model)
    callback_input_name = "cydraCallbackInput"
    callback_setup = (
        f"{parameter.type} memory {callback_input_name} = {typed};\\n"
        f"        {callback_input_name}.{'.'.join(parameter_path[1:])} = abi.encode(cydraStack);"
    )
    return {
        "parameter": parameter,
        "input_name": callback_input_name,
        "setup": declaration + "\\n        " + callback_setup,
        "imports": set(imports) | {(str(stack_path_name), discovered["decoded_type"]), (str(operation_path), discovered["operation_type"])} if operation_path else set(imports) | {(str(stack_path_name), discovered["decoded_type"])},
        "typed_call_args": (callback_input_name,) + tuple(target_arguments[1:]),
    }


def generate_callback_state_order_test(
    hypothesis: Hypothesis,
    experiment: Experiment,
    target_import: str,
    target_type: str,
    output_path: str | Path,
    contract_model: ContractModel,
) -> Path:
    """Render a generic one-shot reentrant callback experiment.

    The harness treats the caller as the callback-capable contract. It re-enters
    the same externally callable target with the same ABI payload exactly once.
    No target function names, callback interfaces, or vulnerability-specific
    arguments are hard-coded here; all target call shape comes from ContractModel
    and the bound Experiment inputs.
    """
    function = next(
        (item for item in contract_model.functions if item.name == hypothesis.target_function),
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

    constructor_arguments = [
        _constructor_argument(parameter)
        for parameter in (contract_model.constructor.parameters if contract_model.constructor else ())
    ]
    constructor_call = (
        f"new {target_type}({', '.join(constructor_arguments)})"
        if constructor_arguments
        else f"new {target_type}()"
    )

    # abi.encodeCall preserves compiler-checked tuple/struct ABI types and avoids
    # inventing canonical signature text for source-defined parameters.
    argument_text = ", ".join(arguments)
    initial_call = f"abi.encodeCall(target.{function.name}, ({argument_text}))"

    pragma = contract_model.pragma or "^0.8.20"
    path = Path(output_path)
    target_import = _layout_aware_import_path(target_import, path)

    source = f'''// SPDX-License-Identifier: UNLICENSED
pragma solidity {pragma};
// Hypothesis: {hypothesis.hypothesis_id}
// Experiment: {experiment.experiment_id}
// Generic callback-order experiment: caller is a contract that re-enters the
// same target call exactly once from its fallback. The harness contains no
// target-specific callback interface or function name.
import {{Test}} from "forge-std/Test.sol";
import {{ {target_type} }} from "{target_import}";

contract CydraReentrantCaller {{
    address internal immutable target;
    bytes internal immutable callData;
    bool public callbackObserved;
    bool public reentrySucceeded;
    bool internal entered;

    constructor(address target_, bytes memory callData_) {{
        target = target_;
        callData = callData_;
    }}

    function invoke() external {{
        (bool ok,) = target.call(callData);
        require(ok, "initial target call reverted");
    }}

    fallback() external {{
        callbackObserved = true;
        if (!entered) {{
            entered = true;
            (reentrySucceeded,) = target.call(callData);
        }}
    }}
}}

contract CydraCallbackStateOrderTest is Test {{
    {target_type} internal target;
    CydraReentrantCaller internal attacker;

    function setUp() public {{
        target = {constructor_call};
        attacker = new CydraReentrantCaller(
            address(target),
            {initial_call}
        );
    }}

    function testCallbackStateOrder() public {{
        attacker.invoke();
        assertTrue(attacker.callbackObserved(), "target did not invoke the caller-controlled callback");
        assertTrue(attacker.reentrySucceeded(), "reentrant call was blocked or reverted");
    }}
}}
'''
    return _write_test(source, path)
