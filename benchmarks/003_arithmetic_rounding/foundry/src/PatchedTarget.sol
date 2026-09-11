// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

/// @notice Patched control for the arithmetic-rounding benchmark.
contract ArithmeticRoundingFixture {
    uint256 public constant SCALE = 1000;

    function quoteMint(uint256 assets) external pure returns (uint256) {
        // Patched: floor division preserves the stated invariant.
        return (assets * SCALE) / 997;
    }
}
