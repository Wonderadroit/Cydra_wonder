from __future__ import annotations

from pathlib import Path

from .models import Hypothesis


def generate_cross_contract_attribution_test(
    hypothesis: Hypothesis, output: Path, target_import: str
) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    content = f"""// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "{target_import}";

contract CydraCrossContractAttributionTest {{
    function testCrossContractAttribution() public {{
        MockHookToken token = new MockHookToken(100);
        OlympusTreasury treasury = new OlympusTreasury();

        treasury.seedDebt(token, address(this), 100);
        token.configureHook(address(treasury), 50);

        treasury.repayLoan(token, 100);

        require(
            treasury.reserveDebt(address(token), address(this)) == 100,
            "debt reduced by unrelated inflow"
        );
    }}
}}
"""
    output.write_text(content, encoding="utf-8")
    return output
