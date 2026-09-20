// SPDX-License-Identifier: MIT
pragma solidity 0.8.26;

contract EthosAttestation {
  function createAttestation(
    uint256 profileId,
    uint256 randValue,
    bytes calldata account,
    bytes calldata service,
    bytes calldata evidence,
    bytes calldata signature
  ) external {
    validateAndSaveSignature(
      _keccakForCreateAttestation(profileId, randValue, account, service, evidence),
      signature
    );
  }

  function _keccakForCreateAttestation(
    uint256 profileId,
    uint256 randValue,
    bytes calldata account,
    bytes calldata service,
    bytes calldata evidence
  ) private pure returns (bytes32) {
    return keccak256(abi.encodePacked(profileId, randValue, account, service, evidence));
  }

  function validateAndSaveSignature(bytes32 messageHash, bytes calldata signature) internal virtual {}
}
