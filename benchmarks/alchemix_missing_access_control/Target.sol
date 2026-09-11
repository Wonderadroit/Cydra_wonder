// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.0;

/// Minimal benchmark fixture reconstructed from the public Alchemix
/// "Missing Access Control" case. It intentionally models only the
/// authorization boundary needed for the first CYDRA milestone.
contract AlchemixAccessControlFixture {
    address public governance;
    mapping(address => bool) public whiteList;

    modifier onlyGov() {
        require(msg.sender == governance, "!governance");
        _;
    }

    constructor() {
        governance = msg.sender;
    }

    function setGovernance(address next) external onlyGov {
        governance = next;
    }

    // Historical case pattern: privileged whitelist mutation without the
    // authorization boundary used by its sibling administrative operation.
    function setWhitelist(address account, bool state) external {
        whiteList[account] = state;
    }
}
