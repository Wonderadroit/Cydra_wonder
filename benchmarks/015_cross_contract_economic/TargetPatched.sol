// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract AssetToken {
    mapping(address => uint256) public balanceOf;
    function mint(address to, uint256 amount) external { balanceOf[to] += amount; }
    function transfer(address to, uint256 amount) external returns (bool) {
        require(balanceOf[msg.sender] >= amount, "balance");
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
        return true;
    }
}

contract Strategy {
    AssetToken public immutable asset;
    constructor(AssetToken a) { asset = a; }
    function seed(uint256 amount) external { asset.mint(address(this), amount); }
    function harvest(uint256 requested) external returns (uint256 reported) {
        uint256 delivered = requested > 10 ? requested - 10 : requested;
        asset.transfer(msg.sender, delivered);
        return delivered;
    }
}

contract Vault {
    AssetToken public immutable asset;
    Strategy public immutable strategy;
    uint256 public accountedAssets;
    uint256 public totalShares;
    mapping(address => uint256) public shares;

    constructor(AssetToken a, Strategy s) { asset = a; strategy = s; }

    function seed(uint256 amount) external {
        asset.mint(address(this), amount);
        accountedAssets += amount;
        totalShares += amount;
        shares[msg.sender] += amount;
    }

    function syncStrategy(uint256 requested) external {
        uint256 reported = strategy.harvest(requested);
        accountedAssets += reported;
    }

    function withdraw(uint256 amount) external {
        require(shares[msg.sender] >= amount, "shares");
        require(accountedAssets >= amount, "accounting");
        shares[msg.sender] -= amount;
        totalShares -= amount;
        accountedAssets -= amount;
        require(asset.transfer(msg.sender, amount), "transfer");
    }
}
