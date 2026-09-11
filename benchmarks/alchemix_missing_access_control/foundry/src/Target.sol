// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

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

    function setWhitelist(address account, bool state) external {
        whiteList[account] = state;
    }
}
