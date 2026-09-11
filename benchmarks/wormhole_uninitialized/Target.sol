// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

/// Minimal reconstructed fixture inspired by Immunefi's historical Wormhole
/// uninitialized implementation bug. It isolates the lifecycle boundary:
/// an implementation remains uninitialized and its initializer assigns the
/// privileged guardian set to the first caller.
contract WormholeInitializationFixture {
    address public guardian;

    function initialize(address nextGuardian) external {
        guardian = nextGuardian;
    }
}
