pragma solidity ^0.8.0;

contract MultiAuthorizationFixture {
    address public owner;
    address public oracle;
    uint256 public fee;

    // Compatibility surface required by the frozen authorization generator.
    // This is not part of the Check 7 hypotheses.
    mapping(address => bool) private _whiteList;

    function whiteList(address account) external view returns (bool) {
        return _whiteList[account];
    }

    function setWhitelist(address account, bool state) external onlyOwner {
        _whiteList[account] = state;
    }

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
