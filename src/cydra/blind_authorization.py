from __future__ import annotations

from pathlib import Path

from .models import ContractModel, Experiment, Hypothesis
from .planned_call import render_function_call
from .authorization_runtime import security_assertion_marker


def _constructor_argument(parameter) -> str:
    parameter_type = parameter.type.strip()
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
        return "bytes("")"
    if base.startswith("bytes") and base[5:].isdigit():
        return f"{base}(0)"
    # Legacy Solidity permits explicit address-to-contract/interface conversion.
    # This keeps the renderer target-generic without importing a modern test library.
    return f"{base}(address(0x1001))"


def _constructor_arguments(contract_model: ContractModel) -> str:
    constructor = contract_model.constructor
    if constructor is None:
        return ""
    return ", ".join(_constructor_argument(parameter) for parameter in constructor.parameters)


def generate_blind_authorization_test_from_experiment(
    hypothesis: Hypothesis,
    experiment: Experiment,
    target_import: str,
    target_type: str,
    output_path: str | Path,
    contract_model: ContractModel,
) -> Path:
    """Render a one-sided authorization invariant test from the canonical plan.

    The renderer is intentionally independent of forge-std so historical Solidity
    targets can be tested even when their compiler pragma predates current forge-std.
    No patched target, benchmark answer, or target-specific function name is supplied.
    """
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
    constructor_arguments = _constructor_arguments(contract_model)
    pragma = contract_model.pragma or "^0.8.20"
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    marker = security_assertion_marker()

    constructor_encoding = (
        f"abi.encode({constructor_arguments})"
        if constructor_arguments
        else "abi.encode()"
    )
    source = f'''// SPDX-License-Identifier: UNLICENSED
pragma solidity {pragma};
// Hypothesis: {hypothesis.hypothesis_id}
// Experiment: {experiment.experiment_id}
// One-sided invariant test: no patched target or benchmark answer is imported.
import {{ {target_type} }} from "{target_import}";

contract CydraBlindAuthorizationTest {{
    {target_type} internal target;

    function setUp() public {{
        bytes memory init = abi.encodePacked(type({target_type}).creationCode, {constructor_encoding});
        address deployed;
        assembly {{
            deployed := create(0, add(init, 32), mload(init))
        }}
        require(deployed != address(0), "CYDRA target deployment failed");
        target = {target_type}(deployed);
    }}

    function testUnauthorizedCallerCannotMutateModeledAdministrativeState() public {{
        (bool ok,) = address(target).call(
            abi.encodeWithSignature(
                "{function.name}({','.join(parameter.type.split()[0] for parameter in function.parameters)})",
                {arguments}
            )
        );
        require(
            !ok,
            "{marker}: unauthorized caller successfully invoked protected administrative operation"
        );
    }}
}}
'''
    path.write_text(source, encoding="utf-8")
    return path
