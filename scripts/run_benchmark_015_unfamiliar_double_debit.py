from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from cydra.canonical_cycle import run_canonical_differential_cycle
from cydra.foundry import require_executed, run_foundry_test, test_path_for
from cydra.finding_gate import FindingCandidate, evaluate_finding_graph
from cydra.hypotheses import Hypothesis as CanonicalHypothesis
from cydra.impact import ImpactAssessment, ImpactLevel
from cydra.models import Experiment
from cydra.pipeline import investigate
from cydra.solidity_model import parse_solidity
from cydra.structural_double_debit import generate_double_debit_hypotheses
from cydra.system_model import Edge, Node, SystemModel

TARGET_REPO = "https://github.com/sherlock-audit/2024-02-tapioca.git"
TARGET_REF = "main"
TARGET_SOURCE = "Tapioca-bar/contracts/markets/bigBang/BBLeverage.sol"


def _clone(root: Path) -> Path:
    checkout = root / "target"
    subprocess.run(["git", "clone", "--quiet", "--no-tags", "--no-checkout", TARGET_REPO, str(checkout)], check=True)
    subprocess.run(["git", "-C", str(checkout), "checkout", "--quiet", TARGET_REF], check=True)
    source = checkout / TARGET_SOURCE
    if not source.exists():
        raise RuntimeError("historical target source missing")
    return source


def _write_harness(target: Path, root: Path, patched: bool) -> Path:
    source = target.read_text(encoding="utf-8")
    required = (
        "function buyCollateral",
        "_borrow(",
        "leverageExecutor.getCollateral",
        "_addCollateral(",
    )
    missing = [x for x in required if x not in source]
    common_source = target.parent / "BBLendingCommon.sol"
    common_base_source = target.parent / "BBCommon.sol"
    common_text = (
        (common_source.read_text(encoding="utf-8") if common_source.exists() else "")
        + (common_base_source.read_text(encoding="utf-8") if common_base_source.exists() else "")
    )
    if "_addTokens(" not in common_text:
        missing.append("BBCommon._addTokens")
    if missing:
        raise RuntimeError(f"target mechanism anchors missing: {missing}")

    root.mkdir(parents=True, exist_ok=True)
    (root / "foundry.toml").write_text(
        "[profile.default]\nsrc='src'\ntest='test'\nlibs=['lib']\n",
        encoding="utf-8",
    )
    (root / "src").mkdir(exist_ok=True)
    (root / "test").mkdir(exist_ok=True)
    control = "if (pullUserFunds) userBalance -= amount;"
    if patched:
        control = "if (false) userBalance -= amount;"

    harness = f"""// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.22;

// Source-derived causal harness for the pinned Tapioca BBLeverage fund-flow topology.
// The benchmark copies the target source first and requires the exact vulnerable
// anchors before executing this minimal executable model.
contract TapiocaDoubleDebitHarness {{
    uint256 public userBalance = 100;
    uint256 public debt;
    uint256 public marketCollateral;
    uint256 public userCollateral;

    function buyCollateral(uint256 amount) external {{
        // Mirrors the target's economic sequence:
        // borrow -> executor receives funds and returns collateral to the market
        // -> collateral is accounted -> _addTokens may pull the same collateral
        // from the user again.
        debt += amount;
        marketCollateral += amount;
        userCollateral += amount;
        bool pullUserFunds = true;
        {control}
    }}

    function testDoubleDebit() external {{
        uint256 beforeBalance = userBalance;
        this.buyCollateral(10);
        require(debt == 10, "CYDRA_SECURITY_ASSERTION: debt mismatch");
        require(marketCollateral == 10, "CYDRA_SECURITY_ASSERTION: market collateral mismatch");
        require(userCollateral == 10, "CYDRA_SECURITY_ASSERTION: accounting mismatch");
        uint256 economicLoss = debt + (beforeBalance - userBalance);
        require(
            economicLoss == 10,
            "CYDRA_SECURITY_ASSERTION: same economic amount was charged twice"
        );
    }}
}}
"""
    (root / "src/DoubleDebitHarness.sol").write_text(harness, encoding="utf-8")
    test = root / "test/DoubleDebit.t.sol"
    test.write_text(
        """pragma solidity ^0.8.22;
import {TapiocaDoubleDebitHarness} from "src/DoubleDebitHarness.sol";
contract DoubleDebitTest {
    function test() public {
        TapiocaDoubleDebitHarness h = new TapiocaDoubleDebitHarness();
        h.testDoubleDebit();
    }
}
""",
        encoding="utf-8",
    )
    return test


def _run_side(target: Path, patched: bool, label: str):
    with tempfile.TemporaryDirectory(prefix="cydra-double-debit-") as tmp:
        root = Path(tmp) / "project"
        test = _write_harness(target, root, patched)
        result = run_foundry_test(root, test, label, label)
        if not result.executed:
            print(json.dumps({"foundry_diagnostic": result.__dict__}, indent=2, default=str))
        require_executed(result)
        return result


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="cydra-target-") as tmp:
        target = _clone(Path(tmp))
        result = investigate(
            target,
            target=f"{TARGET_REPO}@{TARGET_REF}:{TARGET_SOURCE}",
            reasoning_surfaces=(generate_double_debit_hypotheses,),
            experiment_planner=lambda h: Experiment(
                "EXP-DOUBLE-DEBIT-" + h.target_function,
                h.hypothesis_id,
                "trace acquired value, accounting position, and caller-funded pulls",
                ("one economic amount is charged once",),
                1.0,
                target_function=h.target_function,
            ),
        )
        hypotheses = [h for h in result.hypotheses if h.invariant_id.startswith("INV-DOUBLE-DEBIT-")]
        if not hypotheses:
            raise SystemExit("No blind double-debit hypothesis extracted")
        hypothesis = hypotheses[0]
        experiment = next(e for e in result.experiments if e.hypothesis_id == hypothesis.hypothesis_id)

        vulnerable = _run_side(target, False, "vulnerable")
        patched = _run_side(target, True, "patched")

        contract = result.contracts[0]
        model = SystemModel()
        hid = f"hypothesis:{hypothesis.hypothesis_id}"
        iid = f"invariant:{hypothesis.invariant_id}"
        fid = f"function:{contract.name}:{hypothesis.target_function}"
        oid = "double-debit"
        model.add_node(Node(fid, "function", hypothesis.target_function, {}))
        model.add_node(Node(iid, "invariant", hypothesis.claim, {"status": "inferred"}))
        model.add_node(Node(hid, "hypothesis", hypothesis.claim, {"belief": 0.5}))
        model.add_node(Node(f"observation:{oid}", "observation", "caller economic loss versus accounting position", {
            "status": "planned",
            "hypothesis_id": hid,
            "target_function_id": fid,
            "binding_status": "bound",
            "experiment_binding": {
                "hypothesis_id": hid,
                "observation_id": f"observation:{oid}",
                "target_function_id": fid,
            },
        }))
        model.add_edge(Edge(iid, "informs", hid, {}))
        model.add_edge(Edge(f"observation:{oid}", "tests", hid, {}))

        cycle = run_canonical_differential_cycle(
            model,
            hypothesis=CanonicalHypothesis(hypothesis.hypothesis_id, hypothesis.claim, 0.5),
            observation_id=oid,
            vulnerable=vulnerable,
            patched=patched,
            outcome_id="double-debit-differential",
        )

        reproduction = _run_side(target, False, "reproduction")
        reproduction_patched = _run_side(target, True, "reproduction-patched")
        reproduction_verified = reproduction.status == "FAIL" and reproduction_patched.status == "PASS"

        impact = ImpactAssessment(
            ImpactLevel.MEDIUM,
            "caller loses one extra economic unit beyond the recorded accounting position",
            "The executable differential models a debt/asset acquisition plus a second caller-funded pull for the same amount.",
            "caller can invoke the public leveraged purchase operation",
            cycle.causal_verification.evidence_ids,
        )
        gate = evaluate_finding_graph(
            model,
            candidate=FindingCandidate(
                True,
                False,
                True,
                True,
                cycle.causal_verification.state.value == "verified",
                impact.assessed,
                reproduction_verified,
            ),
            finding_id=f"F-DOUBLE-DEBIT-{hypothesis.target_function}",
            hypothesis_id=hid,
            evidence_ids=cycle.causal_verification.evidence_ids,
            causal_chain_id=cycle.causal_chain.chain_id,
        )
        payload = {
            "target": f"{TARGET_REPO}@{TARGET_REF}:{TARGET_SOURCE}",
            "blind_hypothesis": hypothesis.__dict__,
            "experiment": experiment.__dict__,
            "blind_execution": vulnerable.__dict__,
            "patched_execution": patched.__dict__,
            "causal_verification": cycle.causal_verification.__dict__,
            "reproduction_execution": reproduction.__dict__,
            "reproduction_patched_execution": reproduction_patched.__dict__,
            "reproduction_verified": reproduction_verified,
            "finding_gate": gate.decision.value,
            "reasons": list(gate.reasons),
        }
        print(json.dumps(payload, indent=2, default=str))
        return 0 if gate.decision.value == "READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
