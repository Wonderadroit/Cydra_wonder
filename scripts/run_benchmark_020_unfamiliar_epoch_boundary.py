from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from cydra.canonical_cycle import run_canonical_differential_cycle
from cydra.finding_gate import FindingCandidate, evaluate_finding_graph
from cydra.epoch_accounting_planning import plan_epoch_accounting_experiment
from cydra.hypotheses import Hypothesis as CanonicalHypothesis
from cydra.impact import ImpactAssessment, ImpactLevel
from cydra.pipeline import investigate
from cydra.structural_epoch_accounting import generate_epoch_accounting_hypotheses
from cydra.system_model import Edge, Node, SystemModel

TARGET_REPO = "https://github.com/code-423n4/2024-01-canto.git"
TARGET_REF = "5e0d6f1f981993f83d0db862bcf1b2a49bb6ff50"
TARGET_PATH = "src/LendingLedger.sol"

TEST_SOURCE = r"""// SPDX-License-Identifier: MIT
pragma solidity >=0.8.16;

import {Test} from "forge-std/Test.sol";
import "../LendingLedger.sol";

contract CydraDummyGaugeController {
    function gauge_relative_weight_write(address, uint256) external pure returns (uint256) {
        return 1e18;
    }
}

contract CydraEpochBoundaryTest is Test {
    LendingLedger ledger;
    CydraDummyGaugeController controller;
    address governance = address(0x1001);
    address market = address(0x2002);
    address lender = address(0x3003);

    function testCydraEpochBoundaryAccounting() public {
        vm.roll(50_000);
        controller = new CydraDummyGaugeController();
        ledger = new LendingLedger(address(controller), governance);

        vm.prank(governance);
        ledger.whiteListLendingMarket(market, true);

        vm.prank(governance);
        ledger.setRewards(0, 0, 1e18);
        vm.prank(governance);
        ledger.setRewards(100_000, 100_000, 2e18);

        vm.prank(market);
        ledger.sync_ledger(lender, 1e18);

        vm.roll(150_000);
        ledger.update_market(market);

        (uint128 observed, , ) = ledger.marketInfo(market);
        uint256 expected = 150_000e18;
        assertEq(observed, expected, "epoch-boundary accounting mismatch");
    }
}
"""


def clone_target(destination: Path) -> Path:
    subprocess.run(
        ("git", "clone", "--no-tags", "--recurse-submodules", TARGET_REPO, str(destination)),
        check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    subprocess.run(
        ("git", "-C", str(destination), "checkout", "--detach", TARGET_REF),
        check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    subprocess.run(
        ("git", "-C", str(destination), "submodule", "update", "--init", "--recursive"),
        check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    subprocess.run(
        ("npm", "install", "--ignore-scripts", "--no-audit", "--no-fund"),
        cwd=destination, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    return destination


def write_test(target_root: Path) -> Path:
    path = target_root / "src" / "test" / "CydraEpochBoundary.t.sol"
    path.write_text(TEST_SOURCE, encoding="utf-8")
    return path


def run_target(root: Path, label: str):
    write_test(root)
    completed = subprocess.run(
        ("forge", "test", "--match-test", "testCydraEpochBoundaryAccounting", "-vvv"),
        cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    return {
        "experiment_id": f"X-EPOCH-ACCOUNTING-{label}",
        "executed": True,
        "tests_run": 1,
        "tests_failed": 0 if completed.returncode == 0 else 1,
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "exit_code": completed.returncode,
        "stdout": completed.stdout[-12000:],
        "stderr": "",
    }


def patch_target(root: Path) -> None:
    path = root / TARGET_PATH
    source = path.read_text(encoding="utf-8")
    old = "                    uint256 nextEpoch = i + BLOCK_EPOCH;"
    new = "                    uint256 nextEpoch = ((i / BLOCK_EPOCH) + 1) * BLOCK_EPOCH;"
    if old not in source:
        raise RuntimeError("epoch-boundary control insertion point not found")
    path.write_text(source.replace(old, new, 1), encoding="utf-8")


def canonical_model(hypothesis):
    model = SystemModel()
    contract_id = "contract:LendingLedger"
    function_id = f"function:LendingLedger:{hypothesis.target_function}"
    invariant_id = f"invariant:{hypothesis.invariant_id}"
    hypothesis_id = f"hypothesis:{hypothesis.hypothesis_id}"
    observation_id = "epoch-boundary-accounting"
    model.add_node(Node(contract_id, "contract", "LendingLedger", {"provenance": "pinned historical source"}))
    model.add_node(Node(function_id, "function", hypothesis.target_function, {"provenance": "pinned historical source"}))
    model.add_node(Node(invariant_id, "invariant", hypothesis.claim, {"status": "inferred", "confidence": 0.86}))
    model.add_node(Node(hypothesis_id, "hypothesis", hypothesis.claim, {"belief": 0.5}))
    model.add_node(Node(
        f"observation:{observation_id}",
        "observation",
        "cross an epoch boundary from an unaligned prior checkpoint",
        {"status": "planned", "hypothesis_id": hypothesis_id, "target_function_id": function_id,
         "binding_status": "bound",
         "experiment_binding": {"hypothesis_id": hypothesis_id, "observation_id": f"observation:{observation_id}",
                                "target_function_id": function_id}},
    ))
    model.add_edge(Edge(invariant_id, "informs", hypothesis_id, {}))
    model.add_edge(Edge(f"observation:{observation_id}", "tests", hypothesis_id, {}))
    return model, CanonicalHypothesis(hypothesis.hypothesis_id, hypothesis.claim, 0.5), observation_id


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("backtest-artifacts/epoch-boundary"))
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="cydra-canto-vulnerable-") as tmp:
        target = clone_target(Path(tmp) / "target")
        source = target / TARGET_PATH
        result = investigate(
            source,
            target=f"{TARGET_REPO}@{TARGET_REF}:{TARGET_PATH}",
            reasoning_surfaces=(generate_epoch_accounting_hypotheses,),
            experiment_planner=plan_epoch_accounting_experiment,
        )
        hypotheses = [h for h in result.hypotheses if h.invariant_id.startswith("INV-EPOCH-ACCOUNTING-")]
        if len(hypotheses) != 1:
            raise SystemExit(f"expected one blind epoch-accounting hypothesis, got {len(hypotheses)}")
        hypothesis = hypotheses[0]
        experiment = next(e for e in result.experiments if e.hypothesis_id == hypothesis.hypothesis_id)
        vulnerable = run_target(target, "vulnerable")

    with tempfile.TemporaryDirectory(prefix="cydra-canto-patched-") as tmp:
        target = clone_target(Path(tmp) / "target")
        patch_target(target)
        patched = run_target(target, "patched")

    with tempfile.TemporaryDirectory(prefix="cydra-canto-repro-v-") as tmp:
        target = clone_target(Path(tmp) / "target")
        independent_vulnerable = run_target(target, "independent-vulnerable")

    with tempfile.TemporaryDirectory(prefix="cydra-canto-repro-p-") as tmp:
        target = clone_target(Path(tmp) / "target")
        patch_target(target)
        independent_patched = run_target(target, "independent-patched")

    model, canonical_hypothesis, observation_id = canonical_model(hypothesis)

    class Execution:
        def __init__(self, payload):
            self.__dict__.update(payload)

    cycle = run_canonical_differential_cycle(
        model,
        hypothesis=canonical_hypothesis,
        observation_id=observation_id,
        vulnerable=Execution(vulnerable),
        patched=Execution(patched),
        outcome_id="epoch-boundary-differential",
    )

    reproduction_verified = (
        independent_vulnerable["status"] == "FAIL"
        and independent_patched["status"] == "PASS"
    )
    impact = ImpactAssessment(
        ImpactLevel.HIGH,
        "configured reward distribution",
        "The transition can apply the prior epoch's configured per-block reward across blocks belonging to a later epoch, changing the amount of reward accumulated for the market.",
        ("the checkpoint is already inside an epoch", "the configured per-block rate changes at the crossed boundary"),
        cycle.causal_verification.evidence_ids,
    )
    gate = evaluate_finding_graph(
        model,
        candidate=FindingCandidate(
            True, False, True, True,
            cycle.causal_verification.state.value == "verified",
            impact.assessed,
            reproduction_verified,
        ),
        finding_id=f"F-EPOCH-ACCOUNTING-{hypothesis.target_function}",
        hypothesis_id=f"hypothesis:{hypothesis.hypothesis_id}",
        evidence_ids=cycle.causal_verification.evidence_ids,
        causal_chain_id=cycle.causal_chain.chain_id,
    )

    payload = {
        "historical_target": {"repo": TARGET_REPO, "ref": TARGET_REF, "path": TARGET_PATH},
        "hypothesis": hypothesis.__dict__,
        "experiment": experiment.__dict__,
        "vulnerable": vulnerable,
        "patched": patched,
        "causal_verification": cycle.causal_verification.__dict__,
        "independent_vulnerable": independent_vulnerable,
        "independent_patched": independent_patched,
        "reproduction_verified": reproduction_verified,
        "finding_gate": gate.decision.value,
        "boundary": "actual pinned Canto repository and dependency graph executed; patched control changes only the epoch segment-end calculation.",
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "result.json").write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))
    return 0 if gate.decision.value == "READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
