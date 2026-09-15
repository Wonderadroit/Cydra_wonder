from __future__ import annotations

from pathlib import Path

from .models import ContractModel, Hypothesis, ParameterModel


SUPPORTED_VALUE_TYPES = {
    "address",
    "address payable",
    "bool",
    "string",
    "bytes",
    *{f"uint{i}" for i in range(8, 257, 8)},
    *{f"int{i}" for i in range(8, 257, 8)},
    *{f"bytes{i}" for i in range(1, 33)},
}


def _argument(parameter: ParameterModel) -> str:
    parameter_type = parameter.type.strip()
    if parameter_type.endswith("[]") or "[" in parameter_type:
        raise ValueError(f"unsupported structural authorization argument type: {parameter_type}")
    if parameter_type == "address payable":
        return "payable(address(0xCAFE))"
    if parameter_type == "address":
        return "address(0xCAFE)"
    if parameter_type == "bool":
        return "false"
    if parameter_type.startswith("uint"):
        return "1"
    if parameter_type.startswith("int"):
        return "1"
    if parameter_type == "string":
        return '"CYDRA"'
    if parameter_type == "bytes":
        return "bytes(\"\")"
    if parameter_type.startswith("bytes"):
        return f"{parameter_type}(hex\"01\")"
    raise ValueError(f"unsupported structural authorization argument type: {parameter_type}")


def _interface_parameter(parameter: ParameterModel, index: int) -> str:
    parameter_type = parameter.type.strip()
    if parameter_type not in SUPPORTED_VALUE_TYPES:
        raise ValueError(f"unsupported structural authorization interface type: {parameter_type}")
    name = parameter.name or f"arg{index}"
    return f"{parameter_type} {name}"


def generate_structural_authorization_test(
    hypothesis: Hypothesis,
    contract_model: ContractModel,
    target_import: str,
    target_type: str,
    output_path: str | Path,
) -> Path:
    if hypothesis.invariant_id != "INV-AUTH-001":
        raise ValueError(f"Unsupported invariant for structural authorization execution: {hypothesis.invariant_id}")
    function = next((item for item in contract_model.functions if item.name == hypothesis.target_function), None)
    if function is None:
        raise ValueError(f"Model has no target function: {hypothesis.target_function}")
    if function.visibility not in {"public", "external"}:
        raise ValueError(f"authorization target {function.name} is not externally callable")
    if contract_model.constructor and contract_model.constructor.parameters:
        raise ValueError("structural authorization execution currently requires a zero-argument constructor")

    interface_parameters = ", ".join(
        _interface_parameter(parameter, index) for index, parameter in enumerate(function.parameters)
    )
    arguments = ", ".join(_argument(parameter) for parameter in function.parameters)
    interface_name = "CydraStructuralAuthTarget"
    pragma = contract_model.pragma or "^0.8.20"
    source = f'''// SPDX-License-Identifier: UNLICENSED
pragma solidity {pragma};
// Hypothesis: {hypothesis.hypothesis_id}
// Typed structural authorization experiment. The callable signature and
// argument values are derived from ContractModel; no benchmark function name
// or selector is hardcoded here.
import {{Test}} from "forge-std/Test.sol";
import {{ {target_type} }} from "{target_import}";

interface {interface_name} {{
    function {function.name}({interface_parameters}) external;
}}

contract CydraAuthInvariantTest is Test {{
    {target_type} internal target;
    address internal attacker = address(0xBEEF);

    function setUp() public {{
        target = new {target_type}();
    }}

    function testUnauthorizedCallerMutationSurface() public {{
        vm.record();
        vm.prank(attacker);
        {interface_name}(address(target)).{function.name}({arguments});
        (bytes32[] memory reads, bytes32[] memory writes) = vm.accesses(address(target));
        reads;
        assertGt(writes.length, 0, "candidate call did not mutate target storage");
    }}
}}
'''
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path
