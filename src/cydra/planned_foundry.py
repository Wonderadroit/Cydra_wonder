from __future__ import annotations

from pathlib import Path

from .models import ContractModel, Experiment, Hypothesis
from .planned_call import render_function_call


def generate_authorization_test_from_experiment(
    hypothesis: Hypothesis,
    experiment: Experiment,
    target_import: str,
    target_type: str,
    output_path: str | Path,
    contract_model: ContractModel,
) -> Path:
    """Generate an authorization experiment from the canonical Experiment plan.

    The Experiment owns the ordered ABI vector. This renderer deliberately does not
    reconstruct arguments from the hypothesis or benchmark name, so compiler-derived
    constraints can reach the actual Foundry call without class-specific argument
    heuristics.
    """
    if hypothesis.invariant_id != "INV-AUTH-001":
        raise ValueError(f"Unsupported invariant for Foundry generation: {hypothesis.invariant_id}")
    if experiment.hypothesis_id != hypothesis.hypothesis_id:
        raise ValueError(
            f"experiment/hypothesis mismatch: {experiment.hypothesis_id} != {hypothesis.hypothesis_id}"
        )

    function = next(
        (candidate for candidate in contract_model.functions if candidate.name == hypothesis.target_function),
        None,
    )
    if function is None:
        raise ValueError(f"Model has no target function: {hypothesis.target_function}")

    call = render_function_call(experiment, function)
    signature_types = ", ".join(parameter.type.split()[0] for parameter in function.parameters)
    arguments = call.removeprefix(f"target.{function.name}(").removesuffix(");")
    pragma = contract_model.pragma or "^0.8.20"
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    source = f'''// SPDX-License-Identifier: UNLICENSED
pragma solidity {pragma};
// Hypothesis: {hypothesis.hypothesis_id}
// Experiment: {experiment.experiment_id}
// Planned inputs are authoritative for this concrete target call.
import {{Test}} from "forge-std/Test.sol";
import {{ {target_type} }} from "{target_import}";

contract CydraAuthInvariantTest is Test {{
    {target_type} internal target;
    address internal attacker = address(0xBEEF);

    function setUp() public {{
        target = new {target_type}();
    }}

    function testUnauthorizedCallerMutationSurface() public {{
        vm.record();
        vm.prank(attacker);
        bool ok;
        try target.{function.name}({arguments}) {{
            ok = true;
        }} catch {{
            ok = false;
        }}
        (bytes32[] memory reads, bytes32[] memory writes) = vm.accesses(address(target));
        reads;
        assertTrue(ok, "candidate call reverted; unauthorized mutation not demonstrated");
        assertGt(writes.length, 0, "candidate call did not mutate target storage");
    }}
}}
'''
    path.write_text(source, encoding="utf-8")
    return path
