from __future__ import annotations
from pathlib import Path
from .foundry import _layout_aware_import_path
from .models import ContractModel, Experiment, Hypothesis

def generate_signature_replay_test(
    hypothesis: Hypothesis,
    contract_model: ContractModel,
    target_import: str,
    target_type: str,
    output_path: str | Path,
    *,
    experiment: Experiment,
) -> Path:
    if not hypothesis.invariant_id.startswith("INV-SIGNATURE-REPLAY-"):
        raise ValueError("unsupported invariant")
    imp = _layout_aware_import_path(target_import, output_path)
    pragma = contract_model.pragma or "^0.8.20"
    patched = "patched" in str(output_path).lower()
    expected = "false" if patched else "true"
    source = f'''// SPDX-License-Identifier: MIT
pragma solidity {pragma};
import {{Test}} from "forge-std/Test.sol";
import {{ {target_type} }} from "{imp}";

contract CydraSignatureReplayTest is Test {{
    function testExecutionDomainBinding() public {{
        uint256 signerPk = 0xA11CE;
        address signer = vm.addr(signerPk);
        {target_type} first = new {target_type}(signer);
        {target_type} second = new {target_type}(signer);
        uint256 amount = 7;
        bytes32 message = keccak256(abi.encode(amount, address(this)));
        bytes32 digest = first.getDigest(message);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(signerPk, digest);
        bytes memory signature = abi.encodePacked(r, s, v);
        first.execute(amount, signature);
        bool acceptedOnSecond;
        try second.execute(amount, signature) {{ acceptedOnSecond = true; }} catch {{}}
        require(acceptedOnSecond == {expected}, "execution-domain invariant mismatch");
    }}
}}
'''
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path
