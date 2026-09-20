from __future__ import annotations

from pathlib import Path

from .foundry import _layout_aware_import_path
from .models import ContractModel, Experiment, Hypothesis


def generate_weighted_average_rounding_test(
    hypothesis: Hypothesis,
    contract_model: ContractModel,
    target_import: str,
    target_type: str,
    output_path: str | Path,
    *,
    experiment: Experiment | None = None,
    callable_name: str | None = None,
) -> Path:
    if hypothesis.invariant_id != "INV-ROUND-001":
        raise ValueError("unsupported invariant for weighted-average rounding execution")
    if experiment is not None and experiment.hypothesis_id != hypothesis.hypothesis_id:
        raise ValueError("experiment/hypothesis mismatch")

    # The vulnerable and patched revisions may expose the same structural
    # operation under different source-level names.  When the caller has
    # already resolved the patched callable structurally, bind to that name
    # rather than requiring the vulnerable hypothesis name to exist in the
    # patched model.  This keeps the execution layer generic: it validates
    # the callable shape, while the investigation layer remains responsible
    # for choosing the structural identity.
    resolved_name = callable_name or hypothesis.target_function
    function = next(
        (item for item in contract_model.functions if item.name == resolved_name),
        None,
    )
    if function is None or len(function.parameters) != 4:
        raise ValueError("weighted-average execution requires four target parameters")
    if not all(parameter.type.startswith("uint") for parameter in function.parameters):
        raise ValueError("weighted-average execution requires four unsigned-integer parameters")

    arguments = experiment.planned_inputs if experiment and experiment.planned_inputs else (
        "100", "2", "99", "1"
    )
    if len(arguments) != 4:
        raise ValueError("weighted-average execution requires four planned arguments")

    target_import = _layout_aware_import_path(target_import, output_path)
    pragma = contract_model.pragma or "^0.8.20"
    source = f'''// SPDX-License-Identifier: UNLICENSED
pragma solidity {pragma};
import {{ {target_type} }} from "{target_import}";

contract CydraRoundingHarness {{
    function callTarget(uint256 a, uint256 b, uint256 c, uint256 d) external pure returns (uint256) {{
        return {target_type}.{resolved_name}(a, b, c, d);
    }}
}}

contract CydraWeightedAverageRoundingTest {{
    CydraRoundingHarness internal target;

    function setUp() public {{
        target = new CydraRoundingHarness();
    }}

    function testWeightedAverageRoundingDirection() public {{
        uint256 valueA = {arguments[0]};
        uint256 weightA = {arguments[1]};
        uint256 valueB = {arguments[2]};
        uint256 weightB = {arguments[3]};
        uint256 numerator = valueA * weightA + valueB * weightB;
        uint256 denominator = weightA + weightB;
        uint256 floorValue = numerator / denominator;
        uint256 ceilingValue = (numerator + denominator - 1) / denominator;
        uint256 observed = target.callTarget(valueA, weightA, valueB, weightB);

        require(numerator % denominator > 0, "test input must be fractional");
        require(observed == ceilingValue, "weighted average rounded below conservative ceiling");
        require(observed >= floorValue, "weighted average below floor");
    }}
}}
'''
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path
