from pathlib import Path
from .foundry import _layout_aware_import_path
from .models import ContractModel, Experiment, Hypothesis

def generate_temporal_precondition_test(hypothesis: Hypothesis, contract_model: ContractModel, target_import: str, target_type: str, output_path: str|Path, *, experiment: Experiment) -> Path:
    if not hypothesis.invariant_id.startswith("INV-TEMPORAL-PRECONDITION-"): raise ValueError("unsupported invariant")
    target_import=_layout_aware_import_path(target_import, output_path)
    pragma=contract_model.pragma or "^0.8.20"
    source=f'''// SPDX-License-Identifier: UNLICENSED\npragma solidity {pragma};\nimport {{ {target_type} }} from "{target_import}";\ncontract CydraTemporalTest {{\n {target_type} internal target;\n function setUp() public {{ target=new {target_type}(); }}\n function testPreconditionCannotBecomeTrueDuringTransition() public {{\n   bytes32 id=keccak256("cydra-temporal");\n   bool reverted; try target.execute(id) { } catch { reverted=true; }\n   require(reverted, "precondition became true only after external call");\n }}}}\n'''
    p=Path(output_path); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(source,encoding="utf-8"); return p
