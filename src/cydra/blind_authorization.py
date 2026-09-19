from __future__ import annotations

from pathlib import Path

from .models import ContractModel, Experiment, Hypothesis
from .planned_call import render_function_call
from .authorization_runtime import security_assertion_marker


def generate_blind_authorization_test_from_experiment(
    hypothesis: Hypothesis,
    experiment: Experiment,
    target_import: str,
    target_type: str,
    output_path: str | Path,
    contract_model: ContractModel,
) -> Path:
    """Render a one-sided authorization invariant test from the canonical plan.

    No patched target, benchmark answer, or target-specific function name is
    supplied. The model and planned ABI vector are the only target-specific
    inputs.
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
    pragma = contract_model.pragma or "^0.8.20"
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    marker = security_assertion_marker()

    source = f'''// SPDX-License-Identifier: UNLICENSED
pragma solidity {pragma};
// Hypothesis: {hypothesis.hypothesis_id}
// Experiment: {experiment.experiment_id}
// One-sided invariant test: no patched target or benchmark answer is imported.
import {{Test}} from "forge-std/Test.sol";
import {{ {target_type} }} from "{target_import}";

contract CydraBlindAuthorizationTest is Test {{
    {target_type} internal target;
    address internal attacker = address(0xBEEF);

    function setUp() public {{
        target = new {target_type}();
    }}

    function testUnauthorizedCallerCannotMutateModeledAdministrativeState() public {{
        vm.record();
        vm.prank(attacker);
        (bool ok,) = address(target).call(
            abi.encodeWithSignature(
                "{function.name}({", ".join(parameter.type.split()[0] for parameter in function.parameters)})",
                {arguments}
            )
        );
        (, bytes32[] memory writes) = vm.accesses(address(target));
        bool unauthorizedMutation = ok && writes.length > 0;
        assertTrue(
            !unauthorizedMutation,
            "{marker}: unauthorized caller mutated modeled administrative state"
        );
    }}
}}
'''
    path.write_text(source, encoding="utf-8")
    return path
