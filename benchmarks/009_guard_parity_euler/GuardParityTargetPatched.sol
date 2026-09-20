// Historical Euler-inspired patched counterpart.
// The only security-relevant change is restoration of the observed postcondition.
pragma solidity ^0.8.20;

contract GuardParityTargetPatched {
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
        checkLiquidity(msg.sender);
    }
}
