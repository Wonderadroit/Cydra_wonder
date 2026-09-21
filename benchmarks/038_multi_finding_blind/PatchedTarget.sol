// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract DualAdminFixture {
    address public governance;
    uint256 public feeBps;
    address public treasury;

    modifier onlyGov() {
        require(msg.sender == governance, "!governance");
        _;
    }

    constructor() {
        governance = msg.sender;
        feeBps = 100;
        treasury = msg.sender;
    }

    function setFeeBps(uint256 nextFeeBps) external onlyGov {
        feeBps = nextFeeBps;
    }

    function setTreasury(address nextTreasury) external onlyGov {
        treasury = nextTreasury;
    }
}
