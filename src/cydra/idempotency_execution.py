from __future__ import annotations

from pathlib import Path

from .foundry import _layout_aware_import_path
from .models import ContractModel, Experiment, Hypothesis


def generate_idempotency_test(
    hypothesis: Hypothesis,
    contract_model: ContractModel,
    target_import: str,
    target_type: str,
    output_path: str | Path,
    *,
    experiment: Experiment,
) -> Path:
    if not hypothesis.invariant_id.startswith("INV-IDEMPOTENCY-"):
        raise ValueError("unsupported invariant")
    target_import = _layout_aware_import_path(target_import, output_path)
    pragma = contract_model.pragma or "^0.8.20"
    source = f'''// SPDX-License-Identifier: UNLICENSED
pragma solidity {pragma};
import {{ {target_type} }} from "{target_import}";

interface ICydraToken {{
    function balanceOf(address account) external view returns (uint256);
}}

contract CydraIdempotencyTest {{
    {target_type} internal target;
    function setUp() public {{ target = new {target_type}(); }}

    function testRepeatedRecordCannotReleaseValueTwice() public {{
        uint256 beforeBalance = ICydraToken(target.token()).balanceOf(address(this));
        uint256[] memory ids = new uint256[](2);
        ids[0] = 0;
        ids[1] = 0;

        bool reverted;
        try target.{hypothesis.target_function}(address(0xBEEF), ids, true) {{ }} catch {{ reverted = true; }}

        uint256 afterBalance = ICydraToken(target.token()).balanceOf(address(this));
        if (reverted) {{
            require(true, "patched target should reject the repeated record");
        }} else {{
            require(afterBalance == beforeBalance + target.amount(), "same record released value more than once");
        }}
    }}
}}
'''
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path
