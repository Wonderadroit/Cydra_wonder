from pathlib import Path
from .foundry import _layout_aware_import_path
from .models import ContractModel, Experiment, Hypothesis

def generate_transfer_accounting_test(hypothesis,contract_model,target_import,target_type,token_type,output_path,*,experiment,patched=False):
    if not hypothesis.invariant_id.startswith("INV-TRANSFER-ACCOUNTING-"): raise ValueError("unsupported invariant")
    target_import=_layout_aware_import_path(target_import,output_path)
    pragma=contract_model.pragma or "^0.8.20"
    source=f'''// SPDX-License-Identifier: UNLICENSED
pragma solidity {pragma};
import {{ {target_type}, FeeTransferToken }} from "{target_import}";

contract CydraTransferAccountingTest {{
    {target_type} internal vault;
    FeeTransferToken internal token;
    function setUp() public {{
        token=new FeeTransferToken();
        vault=new {target_type}(address(token));
        token.mint(address(this),1000);
    }}
    function testInboundCreditMatchesActualReceived() public {{
        vault.deposit(100);
        require(vault.credits(address(this)) == vault.assetBalance(), "credit exceeds actual assets");
    }}
}}
'''
    path=Path(output_path); path.parent.mkdir(parents=True,exist_ok=True); path.write_text(source,encoding="utf-8"); return path
