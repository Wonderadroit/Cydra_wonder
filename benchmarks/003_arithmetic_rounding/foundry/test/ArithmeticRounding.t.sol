// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

import {Test} from "forge-std/Test.sol";
import {ArithmeticRoundingFixture as Vulnerable} from "../src/Target.sol";
import {ArithmeticRoundingFixture as Patched} from "../src/PatchedTarget.sol";

contract ArithmeticRoundingTest is Test {
    function testVulnerableRoundsAboveExactFloor() public {
        Vulnerable target = new Vulnerable();
        uint256 assets = 1;
        uint256 exactFloor = (assets * target.SCALE()) / 997;
        assertGt(target.quoteMint(assets), exactFloor);
    }

    function testPatchedPreservesFloorInvariant() public {
        Patched target = new Patched();
        uint256 assets = 1;
        uint256 exactFloor = (assets * target.SCALE()) / 997;
        assertEq(target.quoteMint(assets), exactFloor);
    }
}
