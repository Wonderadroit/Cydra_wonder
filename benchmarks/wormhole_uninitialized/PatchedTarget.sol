// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

/// Negative control: the deployed implementation is initialized during
/// construction, so an arbitrary caller cannot claim the guardian state.
contract WormholeInitializationFixture {
    address public guardian;
    bool public initialized;

    constructor() {
        guardian = msg.sender;
        initialized = true;
    }

    function initialize(address nextGuardian) external {
        require(!initialized, "already initialized");
        initialized = true;
        guardian = nextGuardian;
    }
}
