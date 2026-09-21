// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract IncentiveQueue {
    uint256 public pending;
    uint256 public rewardPool;
    uint256 public paid;

    constructor() payable { rewardPool = msg.value; }

    function requestWork() external { pending += 1; }

    function commitWork() external {
        require(pending > 0, "no work");
        pending -= 1;
        uint256 reward = 1 ether;
        require(rewardPool >= reward, "empty");
        rewardPool -= reward;
        paid += reward;
        payable(msg.sender).transfer(reward);
    }
}

contract IncentiveQueuePatched {
    uint256 public pending;
    uint256 public rewardPool;
    uint256 public paid;
    uint256 public constant REQUEST_COST = 2 ether;

    constructor() payable { rewardPool = msg.value; }

    function requestWork() external payable {
        require(msg.value >= REQUEST_COST, "request cost");
        pending += 1;
        rewardPool += msg.value;
    }

    function commitWork() external {
        require(pending > 0, "no work");
        pending -= 1;
        uint256 reward = 1 ether;
        require(rewardPool >= reward, "empty");
        rewardPool -= reward;
        paid += reward;
        payable(msg.sender).transfer(reward);
    }
}
