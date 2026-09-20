// Historical Euler-inspired fixture extracted from the documented EToken invariant gap.
// The reasoning target is deliberately generic: sibling state transitions enforce a
// postcondition, while one balance-reducing transition does not.
pragma solidity ^0.8.20;

contract GuardParityTarget {
    mapping(address => uint256) public balance;
    mapping(address => uint256) public debt;
    uint256 public reserves;

    constructor() {
        balance[msg.sender] = 100;
        debt[msg.sender] = 80;
    }

    function checkLiquidity(address account) internal view {
        require(balance[account] >= debt[account], "undercollateralized");
    }

    function withdraw(uint256 amount) external {
        require(balance[msg.sender] >= amount, "insufficient");
        balance[msg.sender] -= amount;
        checkLiquidity(msg.sender);
    }

    function burn(uint256 amount) external {
        require(balance[msg.sender] >= amount, "insufficient");
        balance[msg.sender] -= amount;
        if (debt[msg.sender] >= amount) debt[msg.sender] -= amount;
        checkLiquidity(msg.sender);
    }

    function donateToReserves(uint256 amount) external {
        require(balance[msg.sender] >= amount, "insufficient");
        balance[msg.sender] -= amount;
        reserves += amount;
    }
}
