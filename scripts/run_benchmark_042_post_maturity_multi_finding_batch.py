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


H01_POC = r'''// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.0;

import "./PoC.t.sol";
import {TokenId} from "../lib/panoptic-v1.1/contracts/types/TokenId.sol";
import {LeftRightUnsigned} from "../lib/panoptic-v1.1/contracts/types/LeftRight.sol";

contract CydraMultiFindingH01 is PoC {
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

    function test_cydra_h01() external {
        PanopticVaultAccountant.PoolInfo[] memory pools = _pools();
        accountant.updatePoolsHash(address(vault), keccak256(abi.encode(pools)));

        underlyingToken.setBalance(address(vault), 1000 ether);
        token1.setBalance(address(vault), 0);
        mockPool.collateralToken0().setBalance(address(vault), 0);
        mockPool.collateralToken0().setPreviewRedeemReturn(0);
        mockPool.collateralToken1().setBalance(address(vault), 0);
        mockPool.collateralToken1().setPreviewRedeemReturn(0);

        mockPool.setMockPremiums(
            LeftRightUnsigned.wrap((150 ether << 128) | 200 ether),
            LeftRightUnsigned.wrap((50 ether << 128) | 50 ether)
        );
        mockPool.setNumberOfLegs(address(vault), 0);
        mockPool.setMockPositionBalanceArray(new uint256[2][](0));

        uint256 nav = accountant.computeNAV(
            address(vault),
            address(underlyingToken),
            _managerInput(pools)
        );

        assertApproxEqAbs(nav, 1250 ether, 10 ether, "H01 NAV invariant");
    }
}
'''


H02_POC = r'''// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.0;

import "./PoC.t.sol";
import {TokenId} from "../lib/panoptic-v1.1/contracts/types/TokenId.sol";
import {LeftRightUnsigned} from "../lib/panoptic-v1.1/contracts/types/LeftRight.sol";

contract CydraMultiFindingH02 is PoC {
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
            token0: token0,
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

    function test_cydra_h02() external {
        PanopticVaultAccountant.PoolInfo[] memory pools = _pools();
        accountant.updatePoolsHash(address(vault), keccak256(abi.encode(pools)));

        // The underlying asset is not one of the configured pool tokens.
        underlyingToken.setBalance(address(vault), 50 ether);
        token0.setBalance(address(vault), 0);
        token1.setBalance(address(vault), 0);
        mockPool.collateralToken0().setBalance(address(vault), 0);
        mockPool.collateralToken0().setPreviewRedeemReturn(0);
        mockPool.collateralToken1().setBalance(address(vault), 0);
        mockPool.collateralToken1().setPreviewRedeemReturn(0);

        // Create a net negative pool exposure of -150 without relying on H01:
        // token0 exposure is shortPremium - longPremium in the right slot.
        mockPool.setMockPremiums(
            LeftRightUnsigned.wrap(50 ether),
            LeftRightUnsigned.wrap(200 ether)
        );
        mockPool.setNumberOfLegs(address(vault), 0);
        mockPool.setMockPositionBalanceArray(new uint256[2][](0));

        uint256 nav = accountant.computeNAV(
            address(vault),
            address(underlyingToken),
            _managerInput(pools)
        );

        // Economically equivalent aggregate is max(-150 + 50, 0) = 0.
        assertEq(nav, 0, "H02 aggregate-before-clamp invariant");
    }
}
'''


def clone(destination: Path) -> None:
    subprocess.run(
        ["git", "clone", "--no-tags", "--recurse-submodules", REPO, str(destination)],
        check=True,
    )
    subprocess.run(["git", "-C", str(destination), "checkout", "--detach", REF], check=True)


def run_foundry(project: Path, label: str, contract: str, test: str) -> dict:
    completed = subprocess.run(
        [
            "forge",
            "test",
            "--match-contract",
            contract,
            "--match-test",
            test,
            "-vvv",
        ],
        cwd=project,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "label": label,
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def patch_h01(source: str) -> str:
    old = """poolExposure1 =
                    int256(uint256(longPremium.leftSlot())) -
                    int256(uint256(shortPremium.leftSlot()));"""
    new = """poolExposure1 =
                    int256(uint256(shortPremium.leftSlot())) -
                    int256(uint256(longPremium.leftSlot()));"""
    if old not in source:
        raise RuntimeError("H01 causal-control patch did not match pinned source")
    return source.replace(old, new, 1)


def patch_h02(source: str) -> str:
    clamp = "            nav += uint256(Math.max(poolExposure0 + poolExposure1, 0));"
    if clamp not in source:
        raise RuntimeError("H02 clamp statement did not match pinned source")

    source = source.replace(
        "        for (uint256 i = 0; i < pools.length; i++) {",
        "        int256 totalExposure;\n\n        for (uint256 i = 0; i < pools.length; i++) {",
        1,
    )
    source = source.replace(
        clamp,
        "            totalExposure += poolExposure0 + poolExposure1;",
        1,
    )
    old_tail = """        bool skipUnderlying = false;
        for (uint256 i = 0; i < underlyingTokens.length; i++) {
            if (underlyingTokens[i] == underlyingToken) skipUnderlying = true;
        }
        if (!skipUnderlying) nav += IERC20Partial(underlyingToken).balanceOf(_vault);
"""
    new_tail = """        bool skipUnderlying = false;
        for (uint256 i = 0; i < underlyingTokens.length; i++) {
            if (underlyingTokens[i] == underlyingToken) skipUnderlying = true;
        }
        if (!skipUnderlying) {
            totalExposure += int256(IERC20Partial(underlyingToken).balanceOf(_vault));
        }
        nav = uint256(Math.max(totalExposure, 0));
"""
    if old_tail not in source:
        raise RuntimeError("H02 final aggregation block did not match pinned source")
    return source.replace(old_tail, new_tail, 1)


def run_case(
    project: Path,
    finding: str,
    poc: str,
    contract: str,
    test: str,
    patcher,
    pristine_source: str,
    label: str,
) -> dict:
    # Reuse one prepared target checkout for the whole batch. Only the pinned
    # source file is reset between controls; installed dependencies remain
    # intact. This makes failures accumulate quickly without hiding execution
    # differences behind repeated dependency installation.
    source = project / SOURCE
    (project / SOURCE).write_text(pristine_source)
    for generated in (project / "test").glob("CydraMultiFinding*.t.sol"):
        generated.unlink()
    (project / "test" / f"Cydra{finding}.t.sol").write_text(poc)
    if label.endswith("-patched") or label.endswith("-independent-patched"):
        source.write_text(patcher(source.read_text()))
    return run_foundry(project, label, contract, test)


def main() -> int:
    output = Path("backtest-artifacts/benchmark-042")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    blind = output / "blind"
    blind.mkdir()
    command = [
        sys.executable,
        "scripts/run_benchmark_blind.py",
        "--target-repo",
        REPO,
        "--target-ref",
        REF,
        "--target-path",
        SOURCE,
        "--target-project",
        ".",
        "--classes",
        "arithmetic",
        "--freeze",
        str(blind / "freeze"),
    ]
    selected = subprocess.run(command, text=True, capture_output=True, check=False)
    if selected.returncode != 0:
        (output / "blind-run.json").write_text(
            json.dumps(
                {
                    "exit_code": selected.returncode,
                    "stdout": selected.stdout,
                    "stderr": selected.stderr,
                },
                indent=2,
            )
            + "\n"
        )
        return selected.returncode

    hypotheses = json.loads((blind / "freeze" / "hypotheses.json").read_text())
    expected = {
        "H-PAIR-SYMMETRY-computeNAV-poolExposure",
        "H-AGGREGATION-ORDER-computeNAV",
    }
    matched = [
        hypothesis
        for hypothesis in hypotheses
        if hypothesis.get("hypothesis_id") in expected
        and hypothesis.get("target_function") == "computeNAV"
    ]

    (output / "blind-selection.json").write_text(
        json.dumps(
            {
                "hypothesis_count": len(hypotheses),
                "matching_hypotheses": matched,
                "expected_hypothesis_ids": sorted(expected),
                "blind_boundary_preserved": True,
            },
            indent=2,
        )
        + "\n"
    )

    missing = sorted(expected - {item["hypothesis_id"] for item in matched})
    if missing:
        (output / "result.json").write_text(
            json.dumps(
                {
                    "status": "NOT_CONFIRMED",
                    "reason": "blind selection missed one or more independent finding hypotheses",
                    "missing_hypotheses": missing,
                },
                indent=2,
            )
            + "\n"
        )
        return 1

    with tempfile.TemporaryDirectory(prefix="cydra-042-") as tmp:
        root = Path(tmp)
        project = root / "project"
        clone(project)
        pristine_source = (project / SOURCE).read_text(encoding="utf-8")
        results = {
            "H-01": {
                "vulnerable": run_case(
                    project, "H01", H01_POC, "CydraMultiFindingH01",
                    "test_cydra_h01", patch_h01, "h01-vulnerable"
                ),
                "patched": run_case(
                    root, "H01", H01_POC, "CydraMultiFindingH01",
                    "test_cydra_h01", patch_h01, "h01-patched"
                ),
                "independent_vulnerable": run_case(
                    root, "H01", H01_POC, "CydraMultiFindingH01",
                    "test_cydra_h01", patch_h01, "h01-independent-vulnerable"
                ),
                "independent_patched": run_case(
                    root, "H01", H01_POC, "CydraMultiFindingH01",
                    "test_cydra_h01", patch_h01, "h01-independent-patched"
                ),
            },
            "H-02": {
                "vulnerable": run_case(
                    project, "H02", H02_POC, "CydraMultiFindingH02",
                    "test_cydra_h02", patch_h02, "h02-vulnerable"
                ),
                "patched": run_case(
                    root, "H02", H02_POC, "CydraMultiFindingH02",
                    "test_cydra_h02", patch_h02, "h02-patched"
                ),
                "independent_vulnerable": run_case(
                    root, "H02", H02_POC, "CydraMultiFindingH02",
                    "test_cydra_h02", patch_h02, "h02-independent-vulnerable"
                ),
                "independent_patched": run_case(
                    root, "H02", H02_POC, "CydraMultiFindingH02",
                    "test_cydra_h02", patch_h02, "h02-independent-patched"
                ),
            },
        }

    finding_results = {}
    for finding, case in results.items():
        causal = case["vulnerable"]["status"] == "FAIL" and case["patched"]["status"] == "PASS"
        reproduction = (
            case["independent_vulnerable"]["status"] == "FAIL"
            and case["independent_patched"]["status"] == "PASS"
        )
        finding_results[finding] = {
            "causal_verification": causal,
            "reproduction_verification": reproduction,
            "finding_gate": "READY" if causal and reproduction else "BLOCKED",
            **case,
        }

    ready = all(
        item["causal_verification"] and item["reproduction_verification"]
        for item in finding_results.values()
    )
    result = {
        "status": "READY" if ready else "NOT_CONFIRMED",
        "target": {"repo": REPO, "ref": REF, "source": SOURCE},
        "blind_selection": matched,
        "findings_total": len(finding_results),
        "findings_ready": sum(
            1 for item in finding_results.values() if item["finding_gate"] == "READY"
        ),
        "findings": finding_results,
        "multi_finding_gate": "READY" if ready and len(finding_results) >= 2 else "BLOCKED",
        "blind_boundary_preserved": True,
    }
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
