from pathlib import Path

from cydra.solidity_model import parse_solidity
from cydra.structural_signature_reuse import generate_signature_reuse_hypotheses


def test_signature_reuse_surface_requires_pre_state_guard(tmp_path: Path):
    source = tmp_path / "Target.sol"
    source.write_text(
        """pragma solidity ^0.8.20;
        contract Target {
            mapping(address => bool) public claimed;
            function claim(bytes calldata signature) external {
                require(signature.length > 0);
                _recoverSigner(signature);
                _consume(msg.sender);
            }
            function _recoverSigner(bytes calldata signature) internal pure returns (address) {
                require(signature.length > 0);
                return ecrecover(bytes32(0), 27, bytes32(0), bytes32(0));
            }
            function _consume(address user) internal {
                claimed[user] = true;
            }
        }""",
        encoding="utf-8",
    )
    contract = parse_solidity(source)[0]
    result = generate_signature_reuse_hypotheses(contract)
    assert len(result.hypotheses) == 1
    assert result.hypotheses[0].hypothesis_id == "H-SIGNATURE-REUSE-claim"


def test_signature_reuse_surface_respects_existing_guard(tmp_path: Path):
    source = tmp_path / "Target.sol"
    source.write_text(
        """pragma solidity ^0.8.20;
        contract Target {
            mapping(address => bool) public claimed;
            function claim(bytes calldata signature) external {
                require(signature.length > 0);
                _verify(signature);
                _consume(msg.sender);
            }
            function _verify(bytes calldata signature) internal pure {
                require(signature.length > 0);
                address signer = ecrecover(bytes32(0), 27, bytes32(0), bytes32(0));
                signer;
            }
            function _consume(address user) internal {
                require(!claimed[user]);
                claimed[user] = true;
            }
        }""",
        encoding="utf-8",
    )
    contract = parse_solidity(source)[0]
    result = generate_signature_reuse_hypotheses(contract)
    assert not result.hypotheses
