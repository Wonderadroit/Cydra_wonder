// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

contract ReadOnlyPoolPatched {
    mapping(address => uint256) public balances;
    uint256 public totalSupply;
    uint256 public reserve;
    bool private locked;

    constructor() payable {
        balances[msg.sender] = 100 ether;
        totalSupply = 100 ether;
        reserve = 100 ether;
    }

    modifier notLocked() {
        require(!locked, "reentrant view");
        _;
    }

    function removeLiquidity(uint256 amount) external {
        require(balances[msg.sender] >= amount, "balance");
        balances[msg.sender] -= amount;
        totalSupply -= amount;
        locked = true;

        (bool ok,) = msg.sender.call{value: amount}("");
        require(ok, "send");

        reserve -= amount;
        locked = false;
    }

    function virtualPrice() external view notLocked returns (uint256) {
        return reserve * 1e18 / totalSupply;
    }
}

contract ReentrantObserverPatched {
    ReadOnlyPoolPatched public pool;
    uint256 public observed;
    bool public callbackSucceeded;

    constructor(ReadOnlyPoolPatched _pool) {
        pool = _pool;
    }

    function attack() external {
        pool.removeLiquidity(10 ether);
    }

    receive() external payable {
        try pool.virtualPrice() returns (uint256 price) {
            observed = price;
            callbackSucceeded = true;
        } catch {
            callbackSucceeded = false;
        }
    }
}
