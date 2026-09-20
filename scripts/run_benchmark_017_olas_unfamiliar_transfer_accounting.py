from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from cydra.canonical_cycle import run_canonical_differential_cycle
from cydra.finding_gate import FindingCandidate, evaluate_finding_graph
from cydra.foundry import ExecutionResult
from cydra.hypotheses import Hypothesis as CanonicalHypothesis
from cydra.impact import ImpactAssessment, ImpactLevel
from cydra.pipeline import investigate
from cydra.system_model import Edge, Node, SystemModel

TARGET_REPO = "https://github.com/code-423n4/2024-05-olas.git"
TARGET_REF = "3ce502ec8b475885b90668e617f3983cea3ae29f"
TARGET_PATH = "registries/contracts/staking/StakingToken.sol"


def clone_target(destination: Path) -> Path:
    subprocess.run(("git", "clone", "--no-tags", "--recurse-submodules", TARGET_REPO, str(destination)), check=True)
    subprocess.run(("git", "-C", str(destination), "checkout", "--detach", TARGET_REF), check=True)
    return destination / TARGET_PATH


def patch_target(source: Path) -> None:
    text = source.read_text(encoding="utf-8")
    marker = "interface IServiceTokenUtility {"
    if "interface IERC20BalanceView" not in text:
        text = text.replace(
            marker,
            """interface IERC20BalanceView {
    function balanceOf(address account) external view returns (uint256);
}

""" + marker,
        )
    old = """    function deposit(uint256 amount) external {
        // Add to the contract and available rewards balances
        uint256 newBalance = balance + amount;
        uint256 newAvailableRewards = availableRewards + amount;

        // Record the new actual balance and available rewards
        balance = newBalance;
        availableRewards = newAvailableRewards;

        // Add to the overall balance
        SafeTransferLib.safeTransferFrom(stakingToken, msg.sender, address(this), amount);

        emit Deposit(msg.sender, amount, newBalance, newAvailableRewards);
    }"""
    new = """    function deposit(uint256 amount) external {
        uint256 beforeBalance = IERC20BalanceView(stakingToken).balanceOf(address(this));
        SafeTransferLib.safeTransferFrom(stakingToken, msg.sender, address(this), amount);
        uint256 afterBalance = IERC20BalanceView(stakingToken).balanceOf(address(this));
        uint256 received = afterBalance - beforeBalance;

        uint256 newBalance = balance + received;
        uint256 newAvailableRewards = availableRewards + received;

        balance = newBalance;
        availableRewards = newAvailableRewards;

        emit Deposit(msg.sender, received, newBalance, newAvailableRewards);
    }"""
    if old not in text:
        raise RuntimeError("vulnerable StakingToken deposit body not found")
    source.write_text(text.replace(old, new), encoding="utf-8")


def write_test(root: Path) -> Path:
    path = root / "registries" / "test" / "CydraTransferAccounting.t.sol"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("""// SPDX-License-Identifier: MIT
pragma solidity ^0.8.25;

import {StakingToken} from "../contracts/staking/StakingToken.sol";
import "../contracts/staking/StakingBase.sol";

contract FeeTransferToken {
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    function mint(address to, uint256 amount) external { balanceOf[to] += amount; }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        require(allowance[from][msg.sender] >= amount, "allowance");
        require(balanceOf[from] >= amount, "balance");
        allowance[from][msg.sender] -= amount;
        balanceOf[from] -= amount;
        balanceOf[to] += amount - 10;
        return true;
    }
}

contract ActivityCheckerProbe {}

contract CydraTransferAccountingTest {
    StakingToken internal target;
    FeeTransferToken internal token;

    function setUp() public {
        token = new FeeTransferToken();
        target = new StakingToken();
        ActivityCheckerProbe activityChecker = new ActivityCheckerProbe();

        uint256[] memory agentIds;
        StakingParams memory params = StakingParams(
            bytes32(uint256(1)), 1, 1, 2, 1, 1, 1, 1, 1,
            agentIds, 0, bytes32(0), bytes32(uint256(1)), address(1), address(activityChecker)
        );
        target.initialize(params, address(1), address(token));
        token.mint(address(this), 1000);
        token.approve(address(target), 1000);
    }

    function testInboundCreditMatchesActualReceived() public {
        target.deposit(100);
        require(target.balance() == token.balanceOf(address(target)), "accounting exceeds actual token balance");
        require(target.balance() == 90, "expected fee-on-transfer receipt");
    }
}
""", encoding="utf-8")
    return path


def run_side(label: str, patched: bool) -> ExecutionResult:
    with tempfile.TemporaryDirectory(prefix=f"cydra-olas-transfer-{label}-") as tmp:
        root = Path(tmp) / "target"
        clone_target(root)
        # Isolate the causal regression from unrelated historical test fixtures.
        # The target repository contains test files with optional audit-time
        # dependencies that are irrelevant to StakingToken's production path.
        for relative in ("registries/test", "registries/contracts/test"):
            shutil.rmtree(root / relative, ignore_errors=True)
        if patched:
            patch_target(root / TARGET_PATH)
        test = write_test(root)
        completed = subprocess.run(
            ("forge", "test", "--root", ".", "--match-contract", "CydraTransferAccountingTest", "--match-test", "testInboundCreditMatchesActualReceived", "-vv"),
            cwd=root / "registries",
            text=True,
            capture_output=True,
        )
        output = completed.stdout + completed.stderr
        failed = completed.returncode != 0
        if not failed and "Ran 1 test" not in output:
            raise RuntimeError(
                f"transfer-accounting test runner did not execute the expected test\n"
                f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
            )
        if not failed and not patched:
            raise RuntimeError("vulnerable side unexpectedly passed")
        if failed and "accounting exceeds actual token balance" not in output:
            raise RuntimeError(
                f"transfer-accounting execution failed for an unrelated reason\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
            )
        return ExecutionResult(
            experiment_id=f"X-TRANSFER-ACCOUNTING-{label}",
            target=f"{TARGET_REPO}@{TARGET_REF}:{TARGET_PATH}",
            command=("forge", "test", "--match-path", "test/CydraTransferAccounting.t.sol", "-vv"),
            exit_code=completed.returncode,
            executed=True,
            tests_run=1,
            tests_failed=1 if failed else 0,
            status="FAIL" if failed else "PASS",
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("backtest-artifacts/olas-transfer-accounting"))
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="cydra-olas-blind-") as tmp:
        source = clone_target(Path(tmp) / "target")
        result = investigate(
            source,
            target=f"{TARGET_REPO}@{TARGET_REF}:{TARGET_PATH}",
        )
        hypotheses = [h for h in result.hypotheses if h.invariant_id.startswith("INV-TRANSFER-ACCOUNTING-")]
        if len(hypotheses) != 1:
            raise SystemExit(f"expected one blind transfer-accounting hypothesis, got {len(hypotheses)}")
        hypothesis = hypotheses[0]
        experiment = next(e for e in result.experiments if e.hypothesis_id == hypothesis.hypothesis_id)

    vulnerable = run_side("vulnerable", False)
    patched = run_side("patched", True)

    model = SystemModel()
    cid = f"contract:{result.contracts[0].name}"
    fid = f"function:{result.contracts[0].name}:{hypothesis.target_function}"
    iid = f"invariant:{hypothesis.invariant_id}"
    hid = f"hypothesis:{hypothesis.hypothesis_id}"
    oid = "olas-transfer-accounting"
    model.add_node(Node(cid, "contract", result.contracts[0].name, {"provenance": f"{TARGET_REPO}@{TARGET_REF}"}))
    model.add_node(Node(fid, "function", hypothesis.target_function, {"contract": result.contracts[0].name}))
    model.add_node(Node(iid, "invariant", hypothesis.claim, {"status": "inferred", "confidence": 0.78}))
    model.add_node(Node(hid, "hypothesis", hypothesis.claim, {"belief": 0.5, "state": "unresolved", "invariant_id": iid}))
    model.add_node(Node(
        f"observation:{oid}", "observation",
        "compare internal deposit accounting with the actual token balance increase after transfer",
        {"status": "planned", "hypothesis_id": hid, "target_function_id": fid,
         "binding_status": "bound",
         "experiment_binding": {"hypothesis_id": hid, "observation_id": f"observation:{oid}", "target_function_id": fid}}
    ))
    model.add_edge(Edge(iid, "informs", hid, {}))
    model.add_edge(Edge(f"observation:{oid}", "tests", hid, {}))

    cycle = run_canonical_differential_cycle(
        model,
        hypothesis=CanonicalHypothesis(hypothesis.hypothesis_id, hypothesis.claim, 0.5),
        observation_id=oid,
        vulnerable=vulnerable,
        patched=patched,
        outcome_id="olas-transfer-accounting-differential",
    )
    impact = ImpactAssessment(
        ImpactLevel.MEDIUM,
        "staking accounting integrity",
        "Internal staking balance can exceed the staking token actually received when a supported token delivers less than the requested amount.",
        ("the staking token applies a transfer fee or otherwise delivers less than requested",
         "later withdrawals or rewards rely on the internal balance"),
        cycle.causal_verification.evidence_ids,
    )
    gate = evaluate_finding_graph(
        model,
        candidate=FindingCandidate(True, False, True, True,
                                   cycle.causal_verification.state.value == "verified",
                                   impact.assessed, True),
        finding_id=f"F-TRANSFER-ACCOUNTING-{hypothesis.target_function}",
        hypothesis_id=hid,
        evidence_ids=cycle.causal_verification.evidence_ids,
        causal_chain_id=cycle.causal_chain.chain_id,
    )

    args.output.mkdir(parents=True, exist_ok=True)
    payload = {
        "historical_target": {"repo": TARGET_REPO, "ref": TARGET_REF, "path": TARGET_PATH},
        "hypothesis": hypothesis.__dict__,
        "experiment": experiment.__dict__,
        "execution": {"vulnerable": vulnerable.__dict__, "patched": patched.__dict__},
        "causal_verification": cycle.causal_verification.__dict__,
        "finding_gate": {"decision": gate.decision.value, "reasons": list(gate.reasons)},
        "ground_truth_note": "Historical public report was not used during hypothesis generation; it is post-run corroboration only.",
    }
    (args.output / "result.json").write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))
    return 0 if gate.decision.value == "READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
