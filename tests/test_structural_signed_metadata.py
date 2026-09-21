from pathlib import Path

from cydra.solidity_model import parse_solidity
from cydra.structural_signed_metadata import generate_signed_metadata_hypotheses


def test_signed_metadata_surface_detects_unbound_auxiliary_data(tmp_path: Path):
    source = tmp_path / "Target.sol"
    source.write_text(
        """pragma solidity ^0.8.20;
        contract Target {
            function validate(bytes32 userOpHash, bytes calldata signature)
                external pure returns (address)
            {
                uint48 validUntil = uint48(bytes12(signature[65:77]));
                uint48 validAfter = 0;
                bytes32 hash = keccak256(abi.encodePacked(userOpHash));
                return ecrecover(hash, uint8(signature[64]), bytes32(0), bytes32(0));
            }
        }""",
        encoding="utf-8",
    )
    contract = parse_solidity(source)[0]
    result = generate_signed_metadata_hypotheses(contract)
    assert len(result.hypotheses) == 1
    assert result.hypotheses[0].hypothesis_id == "H-SIGNED-METADATA-validate"


def test_signed_metadata_surface_accepts_bound_metadata(tmp_path: Path):
    source = tmp_path / "Target.sol"
    source.write_text(
        """pragma solidity ^0.8.20;
        contract Target {
            function validate(bytes32 userOpHash, bytes calldata signature)
                external pure returns (address)
            {
                uint48 validUntil = 1;
                uint48 validAfter = 2;
                bytes32 signedHash = keccak256(abi.encodePacked(userOpHash, validUntil, validAfter));
                bytes32 hash = keccak256(abi.encodePacked(signedHash));
                return ecrecover(hash, 27, bytes32(0), bytes32(0));
            }
        }""",
        encoding="utf-8",
    )
    contract = parse_solidity(source)[0]
    result = generate_signed_metadata_hypotheses(contract)
    assert not result.hypotheses
