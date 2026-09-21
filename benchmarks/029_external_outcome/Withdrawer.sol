// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IW {
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function withdraw(uint256 amount) external;
}

contract Withdrawer {
    IW public weth;
    constructor(IW w) { weth = w; }
    function withdraw(uint256 amount) external {
        weth.transferFrom(msg.sender, address(this), amount);
        weth.withdraw(amount);
    }
}
