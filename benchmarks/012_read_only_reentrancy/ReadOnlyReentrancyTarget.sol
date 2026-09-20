// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

interface IObserver {
    function observe() external;
}

contract ReadOnlyPool {
    mapping(address => uint256) public balances;
    uint256 public totalSupply;
    uint256 public reserve;

    constructor() payable {
        balances[msg.sender] = 100 ether;
        totalSupply = 100 ether;
        reserve = 100 ether;
    }

    function removeLiquidity(uint256 amount) external {
        require(balances[msg.sender] >= amount, "balance");
        balances[msg.sender] -= amount;
        totalSupply -= amount;

        (bool ok,) = msg.sender.call{value: amount}("");
        require(ok, "send");

        reserve -= amount;
    }

    function virtualPrice() external view returns (uint256) {
        return reserve * 1e18 / totalSupply;
    }
}

contract ReentrantObserver {
    ReadOnlyPool public pool;
    uint256 public observed;
    bool public callbackSucceeded;

    constructor(ReadOnlyPool _pool) {
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
