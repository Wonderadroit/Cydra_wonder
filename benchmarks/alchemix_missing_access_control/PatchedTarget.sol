// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.0;

/// Negative-control version of the benchmark fixture.
/// The only intended change is restoration of the governance boundary.
contract AlchemixAccessControlPatchedFixture {
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

    function setWhitelist(address account, bool state) external onlyGov {
        whiteList[account] = state;
    }
}
