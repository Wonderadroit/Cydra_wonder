// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract SignatureReplayTarget {
    address public immutable expectedSigner;
    mapping(bytes => bool) public signatureUsed;
    mapping(address => uint256) public authorizedAmount;

    constructor(address signer) {
        expectedSigner = signer;
    }

    function getDigest(bytes32 messageHash) public pure returns (bytes32) {
        return keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", messageHash));
    }

    function execute(uint256 amount, bytes calldata signature) external {
        require(!signatureUsed[signature], "used");
        bytes32 digest = getDigest(keccak256(abi.encode(amount, msg.sender)));
        (bytes32 r, bytes32 s, uint8 v) = _split(signature);
        address recovered = ecrecover(digest, v, r, s);
        require(recovered == expectedSigner, "invalid");
        signatureUsed[signature] = true;
        authorizedAmount[msg.sender] += amount;
    }

    function _split(bytes calldata sig) private pure returns (bytes32 r, bytes32 s, uint8 v) {
        require(sig.length == 65, "signature");
        assembly {
            r := calldataload(sig.offset)
            s := calldataload(add(sig.offset, 32))
            v := byte(0, calldataload(add(sig.offset, 64)))
        }
    }
}
