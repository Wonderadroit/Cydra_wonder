// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract RedemptionRoundingTarget {
    uint256 public totalSupply;
    uint256 public cash;
    mapping(address => uint256) public shares;
    uint256 public lastRedeemTokens;

    function seedScenario() external {
        require(totalSupply == 0, "seeded");
        totalSupply = 4;
        cash = 8;
        shares[msg.sender] = 2;
    }

    function redeemUnderlying(uint256 amount) external {
        uint256 exchangeRate = (cash * 1e18) / totalSupply;
        uint256 redeemTokens = (amount * 1e18) / exchangeRate;
        require(redeemTokens > 0, "zero burn");
        require(shares[msg.sender] >= redeemTokens, "shares");
        require(cash >= amount, "cash");
        shares[msg.sender] -= redeemTokens;
        totalSupply -= redeemTokens;
        cash -= amount;
        lastRedeemTokens = redeemTokens;
    }
}
