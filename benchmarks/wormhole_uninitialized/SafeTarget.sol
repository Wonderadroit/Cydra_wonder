// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

/// Safe negative control for the initialization lifecycle rule.
/// The initializer remains structurally visible, but deployment claims the
/// privileged guardian state before any arbitrary external caller can use it.
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
