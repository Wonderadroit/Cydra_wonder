from __future__ import annotations
from pathlib import Path
from .models import Hypothesis, Experiment

def generate_cross_contract_economic_test(hypothesis: Hypothesis, output: Path, target_import: str) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(f'''// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
import "{{target_import}}";

contract CydraCrossContractEconomicTest {{
    function testCrossContractBacking() public {{
        AssetToken asset = new AssetToken();
        Strategy strategy = new Strategy(asset);
        Vault vault = new Vault(asset, strategy);

        strategy.seed(100);
        vault.seed(100);
        vault.syncStrategy(100);

        require(vault.accountedAssets() <= asset.balanceOf(address(vault)), "accounting exceeds actual backing");
    }}
}}
'''.format(target_import=target_import), encoding="utf-8")
    return output
