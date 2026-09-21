// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

abstract contract KeeperLike {
    uint256 public rewardPool;

    constructor() payable {
        rewardPool = msg.value;
    }

    modifier keep() {
        _;
        uint256 reward = 1 ether;
        require(rewardPool >= reward, "empty reward pool");
        rewardPool -= reward;
        payable(msg.sender).transfer(reward);
    }

    function settle(
        bytes32[] memory ids,
        address[] memory markets,
        uint256[] memory versions,
        uint256[] memory maxCounts
    ) external virtual keep {
        if (
            ids.length != markets.length ||
            ids.length != versions.length ||
            ids.length != maxCounts.length
        ) revert("invalid settle");
        for (uint256 i; i < ids.length; i++) {
            ids[i];
            markets[i];
            versions[i];
            maxCounts[i];
        }
    }
}

contract KeeperLikePatched is KeeperLike {
    constructor() payable KeeperLike() {}

    function settle(
        bytes32[] memory ids,
        address[] memory markets,
        uint256[] memory versions,
        uint256[] memory maxCounts
    ) external override keep {
        if (
            ids.length == 0 ||
            ids.length != markets.length ||
            ids.length != versions.length ||
            ids.length != maxCounts.length
        ) revert("invalid settle");
        for (uint256 i; i < ids.length; i++) {
            ids[i];
            markets[i];
            versions[i];
            maxCounts[i];
        }
    }
}
