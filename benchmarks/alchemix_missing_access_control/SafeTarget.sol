// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

/// Safe authorization negative control.
/// The apparent authorization pattern remains: governance is established,
/// setGovernance is protected, and setWhitelist is externally callable.
/// However, an upstream state gate permanently disables whitelist mutation
/// for arbitrary callers in the deployed state.
contract AlchemixAccessControlSafeFixture {
    address public governance;
    mapping(address => bool) public whiteList;
    bool public whitelistFrozen;

    modifier onlyGov() {
        require(msg.sender == governance, "!governance");
        _;
    }

    constructor() {
        governance = msg.sender;
        whitelistFrozen = true;
    }

    function setGovernance(address next) external onlyGov {
        governance = next;
    }

    function setWhitelist(address account, bool state) external {
        require(!whitelistFrozen, "whitelist frozen");
        whiteList[account] = state;
    }
}
