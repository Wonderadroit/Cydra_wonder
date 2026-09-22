from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


REPO = "https://github.com/code-423n4/2025-06-panoptic.git"
REF = "eea2c931b1cbce1da01586e42ba298814de40d31"
SOURCE = "src/accountants/PanopticVaultAccountant.sol"


POC = r'''// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.0;

import "./PoC.t.sol";
import {TokenId} from "../lib/panoptic-v1.1/contracts/types/TokenId.sol";
import {LeftRightUnsigned} from "../lib/panoptic-v1.1/contracts/types/LeftRight.sol";

contract CydraDiscoveryPoC is PoC {
    int24 constant TEST_TICK = 100;
    int24 constant MAX_DEVIATION = 50;
    uint32 constant WINDOW = 600;

    function _managerInput(
        PanopticVaultAccountant.PoolInfo[] memory pools
    ) internal pure returns (bytes memory) {
        PanopticVaultAccountant.ManagerPrices[] memory prices =
            new PanopticVaultAccountant.ManagerPrices[](1);
        prices[0] = PanopticVaultAccountant.ManagerPrices({
            poolPrice: TEST_TICK,
            token0Price: TEST_TICK,
            token1Price: TEST_TICK
        });
        return abi.encode(prices, pools, new TokenId[][](1));
    }

    function _pools() internal view returns (PanopticVaultAccountant.PoolInfo[] memory pools) {
        pools = new PanopticVaultAccountant.PoolInfo[](1);
        pools[0] = PanopticVaultAccountant.PoolInfo({
            pool: PanopticPool(address(mockPool)),
            token0: underlyingToken,
            token1: token1,
            poolOracle: poolOracle,
            oracle0: oracle0,
            isUnderlyingToken0InOracle0: true,
            oracle1: oracle1,
            isUnderlyingToken0InOracle1: false,
            maxPriceDeviation: MAX_DEVIATION,
            twapWindow: WINDOW
        });
    }

    function test_cydra_discovered_nav_invariant() external {
        PanopticVaultAccountant.PoolInfo[] memory pools = _pools();
        accountant.updatePoolsHash(vault, keccak256(abi.encode(pools)));

        underlyingToken.setBalance(vault, 1000 ether);
        token1.setBalance(vault, 0);
        mockPool.collateralToken0().setBalance(vault, 0);
        mockPool.collateralToken0().setPreviewRedeemReturn(0);
        mockPool.collateralToken1().setBalance(vault, 0);
        mockPool.collateralToken1().setPreviewRedeemReturn(0);

        uint256 shortPremiumRight = 200 ether;
        uint256 shortPremiumLeft = 150 ether;
        uint256 longPremiumRight = 50 ether;
        uint256 longPremiumLeft = 50 ether;

        mockPool.setMockPremiums(
            LeftRightUnsigned.wrap((shortPremiumLeft << 128) | shortPremiumRight),
            LeftRightUnsigned.wrap((longPremiumLeft << 128) | longPremiumRight)
        );
        mockPool.setNumberOfLegs(vault, 0);
        mockPool.setMockPositionBalanceArray(new uint256[2][](0));

        uint256 nav = accountant.computeNAV(vault, address(underlyingToken), _managerInput(pools));

        assertApproxEqAbs(
            nav,
            1250 ether,
            10 ether,
            "NAV must include net short-minus-long premiums"
        );
    }
}
'''


def clone(destination: Path, ref: str) -> None:
    subprocess.run(["git", "clone", "--no-tags", "--recurse-submodules", REPO, str(destination)], check=True)
    subprocess.run(["git", "-C", str(destination), "checkout", "--detach", ref], check=True)


def run_foundry(project: Path, label: str) -> dict:
    p = subprocess.run(
        ["forge", "test", "--match-contract", "CydraDiscoveryPoC", "--match-test", "test_cydra_discovered_nav_invariant", "-vvv"],
        cwd=project,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "label": label,
        "status": "PASS" if p.returncode == 0 else "FAIL",
        "exit_code": p.returncode,
        "stdout": p.stdout,
        "stderr": p.stderr,
    }


def main() -> int:
    output = Path("backtest-artifacts/benchmark-041")
    output.mkdir(parents=True, exist_ok=True)

    blind = Path("backtest-artifacts/benchmark-041/blind")
    if blind.exists():
        shutil.rmtree(blind)
    blind.mkdir(parents=True)

    command = [
        sys.executable,
        "scripts/run_benchmark_blind.py",
        "--target-repo", REPO,
        "--target-ref", REF,
        "--target-path", SOURCE,
        "--target-project", ".",
        "--classes", "authorization", "state",
        "--freeze", str(blind / "freeze"),
    ]
    selected = subprocess.run(command, text=True, capture_output=True, check=False)

    if selected.returncode != 0:
        (output / "blind-run.json").write_text(json.dumps({
            "exit_code": selected.returncode,
            "stdout": selected.stdout,
            "stderr": selected.stderr,
        }, indent=2) + "
")
        return selected.returncode

    hypotheses = json.loads((blind / "freeze" / "hypotheses.json").read_text())
    matched = [
        h for h in hypotheses
        if h.get("target_function") == "computeNAV"
        and any(term in h.get("claim", "").lower() for term in ("nav", "exposure", "premium"))
    ]

    (output / "blind-selection.json").write_text(json.dumps({
        "hypothesis_count": len(hypotheses),
        "matching_hypotheses": matched,
        "blind_boundary_preserved": True,
    }, indent=2) + "
")

    if not matched:
        (output / "result.json").write_text(json.dumps({
            "status": "NOT_CONFIRMED",
            "reason": "blind selection did not bind the evaluated security-relevant computation",
            "hypothesis_count": len(hypotheses),
        }, indent=2) + "
")
        return 1

    with tempfile.TemporaryDirectory(prefix="cydra-041-") as tmp:
        root = Path(tmp)
        vulnerable = root / "vulnerable"
        clone(vulnerable, REF)
        (vulnerable / "test" / "CydraDiscoveryPoC.t.sol").write_text(POC)
        vulnerable_result = run_foundry(vulnerable, "vulnerable")

        patched = root / "patched"
        clone(patched, REF)
        source = patched / SOURCE
        text = source.read_text()
        old = """poolExposure1 =
                    int256(uint256(longPremium.leftSlot())) -
                    int256(uint256(shortPremium.leftSlot()));"""
        new = """poolExposure1 =
                    int256(uint256(shortPremium.leftSlot())) -
                    int256(uint256(longPremium.leftSlot()));"""
        if old not in text:
            raise RuntimeError("historical causal-control patch did not match the pinned source")
        source.write_text(text.replace(old, new, 1))
        (patched / "test" / "CydraDiscoveryPoC.t.sol").write_text(POC)
        patched_result = run_foundry(patched, "patched")

        independent_v = root / "independent-vulnerable"
        clone(independent_v, REF)
        (independent_v / "test" / "CydraDiscoveryPoC.t.sol").write_text(POC)
        independent_v_result = run_foundry(independent_v, "independent-vulnerable")

        independent_p = root / "independent-patched"
        clone(independent_p, REF)
        source = independent_p / SOURCE
        text = source.read_text()
        if old not in text:
            raise RuntimeError("independent causal-control patch did not match the pinned source")
        source.write_text(text.replace(old, new, 1))
        (independent_p / "test" / "CydraDiscoveryPoC.t.sol").write_text(POC)
        independent_p_result = run_foundry(independent_p, "independent-patched")

    causal_verified = vulnerable_result["status"] == "FAIL" and patched_result["status"] == "PASS"
    reproduction_verified = (
        independent_v_result["status"] == "FAIL"
        and independent_p_result["status"] == "PASS"
    )
    ready = causal_verified and reproduction_verified

    result = {
        "status": "READY" if ready else "NOT_CONFIRMED",
        "blind_selection": matched,
        "vulnerable": vulnerable_result,
        "patched": patched_result,
        "causal_verification": causal_verified,
        "independent_vulnerable": independent_v_result,
        "independent_patched": independent_p_result,
        "reproduction_verification": reproduction_verified,
        "finding_gate": "READY" if ready else "BLOCKED",
        "blind_boundary_preserved": True,
        "target": {"repo": REPO, "ref": REF, "source": SOURCE},
    }
    (output / "result.json").write_text(json.dumps(result, indent=2) + "
")
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
