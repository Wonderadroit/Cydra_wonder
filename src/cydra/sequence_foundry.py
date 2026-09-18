from __future__ import annotations

from pathlib import Path

from .models import ContractModel, Experiment, Hypothesis


def generate_sequence_test_from_experiment(
    hypothesis: Hypothesis,
    experiment: Experiment,
    target_import: str,
    target_type: str,
    output_path: str | Path,
    contract_model: ContractModel,
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

    functions = {function.name: function for function in contract_model.functions}
    rendered: list[str] = []
    for index, step in enumerate(experiment.steps):
        if not step.function.strip():
            raise ValueError(f"sequence step {index} has no function")
        function = functions.get(step.function)
        if function is None:
            raise ValueError(f"model has no sequence function: {step.function}")
        if function.visibility not in {"public", "external"}:
            raise ValueError(f"sequence function is not externally callable: {step.function}")
        if len(step.arguments) != len(function.parameters):
            raise ValueError(
                f"sequence input arity mismatch for {step.function}: "
                f"expected {len(function.parameters)}, got {len(step.arguments)}"
            )
        if any(not argument.strip() for argument in step.arguments):
            raise ValueError(f"sequence step {step.function} contains an empty argument")
        arguments = ", ".join(step.arguments)
        rendered.append(f"        vm.prank(attacker);\n        target.{step.function}({arguments});")

    pragma = contract_model.pragma or "^0.8.20"
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    source = f'''// SPDX-License-Identifier: UNLICENSED
pragma solidity {pragma};
// Hypothesis: {hypothesis.hypothesis_id}
// Experiment: {experiment.experiment_id}
// Structured ordered steps are authoritative for this execution.
import {{Test}} from "forge-std/Test.sol";
import {{ {target_type} }} from "{target_import}";

contract CydraSequenceExperimentTest is Test {{
    {target_type} internal target;
    address internal attacker = address(0xBEEF);

    function setUp() public {{
        target = new {target_type}();
    }}

    function testOrderedExperimentSequence() public {{
{chr(10).join(rendered)}
    }}
}}
'''
    path.write_text(source, encoding="utf-8")
    return path
