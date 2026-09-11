// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

/// @notice Minimal arithmetic-rounding benchmark fixture.
/// The vulnerable implementation rounds a mint quote upward, allowing a caller
/// to receive more shares than the exact floor permitted by the invariant.
contract ArithmeticRoundingFixture {
    uint256 public constant SCALE = 1000;

    function quoteMint(uint256 assets) external pure returns (uint256) {
        // Vulnerable: ceil(assets * SCALE / 997) rather than floor(...).
        return (assets * SCALE + 996) / 997;
    }
}
