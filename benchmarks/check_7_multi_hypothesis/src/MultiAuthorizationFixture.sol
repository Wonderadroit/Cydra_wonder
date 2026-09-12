pragma solidity ^0.8.0;

contract MultiAuthorizationFixture {
    address public owner;
    address public oracle;
    uint256 public fee;

    modifier onlyOwner() {
        require(msg.sender == owner, "not owner");
        _;
    }

    constructor() {
        owner = msg.sender;
    }

    function setOwner(address newOwner) external onlyOwner {
        owner = newOwner;
    }

    function setOracle(address newOracle) external {
        oracle = newOracle;
    }

    function updateFee(uint256 newFee) external {
        fee = newFee;
    }
}
