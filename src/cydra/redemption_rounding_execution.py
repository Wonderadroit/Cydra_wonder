from __future__ import annotations
from pathlib import Path
from .models import Hypothesis, Experiment

def generate_redemption_rounding_test(hypothesis: Hypothesis, target_model, target_import: str, target_type: str, output: Path, experiment: Experiment, expected_tokens: int = 2) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    pragma = "^0.8.20"
    output.write_text(f'''// SPDX-License-Identifier: MIT
pragma solidity {pragma};
import "{{target_type}}" from "{{target_import}}";

contract CydraRedemptionRoundingTest {{
    {{target_type}} internal target;

    function setUp() public {{
        target = new {{target_type}}();
    }}

    function testRedemptionRounding() public {{
        target.seedScenario();
        target.redeemUnderlying(3);
        require(target.lastRedeemTokens() == {expected_tokens}, "required burn was rounded down");
    }}
}}
'''.format(target_type=target_type,target_import=target_import), encoding="utf-8")
    return output
