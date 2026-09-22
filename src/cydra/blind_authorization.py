from __future__ import annotations

from pathlib import Path
import re

from .models import ContractModel, Experiment, Hypothesis
from .planned_call import render_function_call
from .authorization_runtime import security_assertion_marker


def _constructor_argument(parameter, *, abi_only: bool = False) -> str:
    parameter_type = str(parameter.type or "").strip()
    if not parameter_type:
        raise ValueError(
            f"constructor parameter {parameter.name or '<unnamed>'} has no resolved Solidity type"
        )
    base = parameter_type.split()[0].rstrip("[]")
    if parameter_type.endswith("[]"):
        return f"new {base}[](0)"
    if parameter_type == "address payable":
        return "payable(address(0x1001))"
    if base == "address":
        return "address(0x1001)"
    if base == "bool":
        return "false"
    if base.startswith(("uint", "int")):
        return "0"
    if base == "string":
        return '""'
    if base == "bytes":
        return 'bytes("")'
    if base.startswith("bytes") and base[5:].isdigit():
        return "bytes32(uint256(1))" if base == "bytes32" else f"{base}(0)"
    # ABI encoding accepts an address for interface/contract constructor\n    # parameters, avoiding extra source imports in historical harnesses.\n    return "address(0x1001)"


def _constructor_arguments(contract_model: ContractModel, *, abi_only: bool = False) -> str:
    constructor = contract_model.constructor
    if constructor is None:
        return ""
    arguments = []
    for parameter in constructor.parameters:
        arguments.append(_constructor_argument(parameter, abi_only=abi_only))
    return ", ".join(arguments)


def generate_blind_authorization_test_from_experiment(
    hypothesis: Hypothesis,
    experiment: Experiment,
    target_import: str,
    target_type: str,
    output_path: str | Path,
    contract_model: ContractModel,
    creation_bytecode: str | None = None,
) -> Path:
    """Render a one-sided authorization invariant test from the canonical plan."""
    if hypothesis.invariant_id != "INV-AUTH-001":
        raise ValueError(
            f"Unsupported invariant for blind authorization generation: {hypothesis.invariant_id}"
        )
    if experiment.hypothesis_id != hypothesis.hypothesis_id:
        raise ValueError(
            f"experiment/hypothesis mismatch: {experiment.hypothesis_id} != {hypothesis.hypothesis_id}"
        )
    function = next(
        (item for item in contract_model.functions if item.name == hypothesis.target_function),
        None,
    )
    if function is None:
        raise ValueError(f"Model has no target function: {hypothesis.target_function}")
    if function.visibility not in {"public", "external"}:
        raise ValueError(f"authorization target {function.name} is not externally callable")

    call = render_function_call(experiment, function)
    arguments = call.removeprefix(f"target.{function.name}(").removesuffix(");")
    constructor_arguments = _constructor_arguments(
        contract_model, abi_only=creation_bytecode is not None
    )
    constructor_encoding = (
        f"abi.encode({constructor_arguments})"
        if constructor_arguments
        else 'bytes("")'
    )
    # Prefer typed deployment for blind authorization harnesses. A raw
    # creation-bytecode path can cause Foundry to synthesize constructor-argument
    # helper structs whose ABI shape is lost for multi-parameter constructors.
    # The target import is already part of the authorized harness boundary, so
    # direct deployment preserves the constructor ABI exactly.
    init_expression = ""
    target_declaration = f"{target_type} internal target;"
    import_line = f'import {{ {target_type} }} from "{target_import}";'
    target_cast = target_type

    pragma = contract_model.pragma or "^0.8.20"
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    state_getter = None
    state_type = None
    try:
        source_text = Path(contract_model.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        source_text = ""
    for written in function.writes:
        match = re.search(
            rf"\b(address(?:\s+payable)?|bool|uint\d*|int\d*)\s+public\s+{re.escape(written)}\s*;",
            source_text,
        )
        if match:
            state_type = match.group(1).strip()
            state_getter = written
            break

    state_view = ""
    if state_getter is not None:
        state_snapshot = f"        {state_type} beforeState = target.{state_getter}();"
        post_state = f"target.{state_getter}()"
        call_assertion = f'''        require(ok, "{security_assertion_marker()}: authorization call reverted before invariant observation");
        require(
            {post_state} == beforeState,
            "{security_assertion_marker()}: unauthorized caller mutated modeled administrative state"
        );'''
    else:
        state_snapshot = ""
        call_assertion = f'''        require(
            !ok,
            "{security_assertion_marker()}: unauthorized caller successfully invoked protected administrative operation"
        );'''

    # Avoid Solidity's `new Target(...)` syntax here. Foundry's preprocessor
    # rewrites nested `new` expressions into generated free-function helpers;
    # those helpers are not parseable by historical Solidity 0.6.x targets.
    # Assemble the target creation bytecode explicitly so constructor execution
    # remains real while the harness stays compiler-version neutral.
    constructor_suffix = (
        f"abi.encode({constructor_arguments})" if constructor_arguments else 'bytes("")'
    )
    source = f'''// SPDX-License-Identifier: UNLICENSED
pragma solidity {pragma};
// Hypothesis: {hypothesis.hypothesis_id}
// Experiment: {experiment.experiment_id}
// One-sided invariant test: no patched target or benchmark answer is imported.
import {{ {target_type} }} from "{target_import}";

contract CydraBlindAuthorizationTest {{
    {target_declaration}

    function _targetCreationCode() internal pure returns (bytes memory) {{
        return type({target_type}).creationCode;
    }}

    function setUp() public {{
        bytes memory initCode = abi.encodePacked(
            _targetCreationCode(),
            {constructor_suffix}
        );
        address deployed;
        assembly {{
            deployed := create(0, add(initCode, 0x20), mload(initCode))
        }}
        require(deployed != address(0), "CYDRA: constructor deployment failed");
        target = {target_type}(deployed);
    }}

    function testUnauthorizedCallerCannotMutateModeledAdministrativeState() public {{
{state_snapshot}
        (bool ok,) = address(target).call(
            abi.encodeWithSignature(
                "{function.name}({','.join(parameter.type.split()[0] for parameter in function.parameters)})",
                {arguments}
            )
        );
{call_assertion}
    }}
}}
'''
    path.write_text(source, encoding="utf-8")
    return path
