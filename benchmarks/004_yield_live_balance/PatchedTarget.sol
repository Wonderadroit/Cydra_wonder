// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

import {MockPoolToken} from "./Pool.sol";

/// Patched control: redemption uses cached book value, not live token balance.
contract StrategyPatched {
    MockPoolToken public immutable pool;
    uint256 public poolCached;
    uint256 public totalSupply;
    mapping(address => uint256) public balanceOf;

    constructor(MockPoolToken pool_) {
        pool = pool_;
    }

    function seed(address holder, uint256 poolAmount, uint256 shareAmount) external {
        pool.mint(address(this), poolAmount);
        poolCached = poolAmount;
        totalSupply = shareAmount;
        balanceOf[holder] = shareAmount;
    }

    function transferShares(address to, uint256 amount) external {
        require(balanceOf[msg.sender] >= amount, "insufficient shares");
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
    }

    function burn(address to) external returns (uint256 poolTokensObtained) {
        uint256 poolCached_ = poolCached;
        uint256 totalSupply_ = totalSupply;
        uint256 burnt = balanceOf[address(this)];
        require(burnt > 0, "no shares");

        balanceOf[address(this)] = 0;
        totalSupply = totalSupply_ - burnt;

        // Patched: unsolicited donations do not change the redemption price.
        poolTokensObtained = poolCached_ * burnt / totalSupply_;
        pool.transfer(to, poolTokensObtained);

        poolCached = poolCached_ - poolTokensObtained;
    }
}
