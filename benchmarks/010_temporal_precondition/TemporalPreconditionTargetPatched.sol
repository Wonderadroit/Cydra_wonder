// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;
contract TemporalPreconditionTarget {
    mapping(bytes32 => uint256) public timestamps;
    function schedule(bytes32 id) external { timestamps[id] = block.timestamp; }
    function isReady(bytes32 id) public view returns (bool) { return timestamps[id] != 0 && timestamps[id] <= block.timestamp; }
    function execute(bytes32 id) external {
        require(isReady(id), "not ready");
        this.schedule(id);
        require(isReady(id), "not ready");
        timestamps[id] = 2;
    }
}
