from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from cydra.canonical_cycle import run_canonical_differential_cycle
from cydra.control_flow_planning import plan_control_flow_experiment
from cydra.finding_gate import FindingCandidate, evaluate_finding_graph
from cydra.hypotheses import Hypothesis as CanonicalHypothesis
from cydra.impact import ImpactAssessment, ImpactLevel
from cydra.pipeline import investigate
from cydra.structural_control_flow import generate_control_flow_hypotheses
from cydra.system_model import Edge, Node, SystemModel

TARGET_REPO = "https://github.com/code-423n4/2023-09-venus.git"
TARGET_REF = "23f5db740d8a794ac563ac32195b675c53042bb4"
TARGET_PATH = "contracts/Tokens/Prime/Prime.sol"

TEST_SOURCE = r"""// SPDX-License-Identifier: BSD-3-Clause
pragma solidity 0.8.19;

import "forge-std/Test.sol";
import "../Prime.sol";

contract CydraAccessControlManager {
    function isAllowedToCall(address, string memory) external pure returns (bool) {
        return true;
    }
}

contract CydraControlFlowTest is Test {
    Prime prime;
    CydraAccessControlManager accessControl;
    address user1 = address(0x1001);
    address user2 = address(0x1002);

    function _setup() internal {
        accessControl = new CydraAccessControlManager();
        prime = new Prime(address(0x2001), address(0x2002), 1);

        prime.initialize(
            address(0x3001),
            address(0x3002),
            0,
            1,
            2,
            address(accessControl),
            address(0x3003),
            address(0x3004),
            address(0x3005),
            address(0x3006),
            10
        );

        prime.setLimit(10, 10);
        prime.issue(false, _single(user1));
        prime.issue(false, _single(user2));

        // Starting a new score-update round marks neither user as processed.
        prime.updateAlpha(1, 2);
    }

    function _single(address user) internal pure returns (address[] memory users) {
        users = new address[](1);
        users[0] = user;
    }

    function testCydraControlFlowProgress() public {
        _setup();

        prime.updateScores(_single(user1));

        address[] memory users = new address[](2);
        users[0] = user1;
        users[1] = user2;

        // The first element is already processed. A correct implementation
        // must skip it and still process user2.
        (bool success, ) = address(prime).call{gas: 200_000}(
            abi.encodeWithSignature("updateScores(address[])", users)
        );
        assertTrue(success, "updateScores failed to make progress");
    }
}
"""

REMAPPINGS = """@openzeppelin/=node_modules/@openzeppelin/
@venusprotocol/governance-contracts/=node_modules/@venusprotocol/governance-contracts/
@venusprotocol/isolated-pools/=node_modules/@venusprotocol/isolated-pools/
@venusprotocol/oracle/=node_modules/@venusprotocol/oracle/
forge-std/=lib/forge-std/src/
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
    npm = subprocess.run(
        ("npm", "install", "--ignore-scripts", "--no-audit", "--no-fund"),
        cwd=destination, check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    if npm.returncode != 0:
        raise RuntimeError("npm dependency installation failed:\n" + npm.stdout[-12000:])
    )
    subprocess.run(
        ("forge", "install", "foundry-rs/forge-std", "--no-commit"),
        cwd=destination, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    return destination


def write_harness(root: Path) -> None:
    path = root / "contracts" / "test" / "CydraControlFlow.t.sol"
    path.write_text(TEST_SOURCE, encoding="utf-8")
    (root / "remappings.txt").write_text(REMAPPINGS, encoding="utf-8")


def run_target(root: Path, label: str) -> dict:
    write_harness(root)
    completed = subprocess.run(
        ("forge", "test", "--match-test", "testCydraControlFlowProgress", "-vvv"),
        cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    return {
        "experiment_id": f"X-CONTROL-FLOW-{label}",
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
    old = "            if (isScoreUpdated[nextScoreUpdateRoundId][user]) continue;"
    new = (
        "            if (isScoreUpdated[nextScoreUpdateRoundId][user]) {\n"
        "                unchecked {\n"
        "                    i++;\n"
        "                }\n"
        "                continue;\n"
        "            }"
    )
    if old not in source:
        raise RuntimeError("control-flow causal insertion point not found")
    path.write_text(source.replace(old, new, 1), encoding="utf-8")


def canonical_model(hypothesis):
    model = SystemModel()
    contract_id = "contract:Prime"
    function_id = f"function:Prime:{hypothesis.target_function}"
    invariant_id = f"invariant:{hypothesis.invariant_id}"
    hypothesis_id = f"hypothesis:{hypothesis.hypothesis_id}"
    observation_id = "continue-bypasses-progress"

    model.add_node(Node(contract_id, "contract", "Prime", {"provenance": "pinned historical source"}))
    model.add_node(Node(function_id, "function", hypothesis.target_function, {"provenance": "pinned historical source"}))
    model.add_node(Node(invariant_id, "invariant", hypothesis.claim, {"status": "inferred", "confidence": 0.87}))
    model.add_node(Node(hypothesis_id, "hypothesis", hypothesis.claim, {"belief": 0.5}))
    model.add_node(
        Node(
            f"observation:{observation_id}",
            "observation",
            "a previously processed user is supplied before a still-unprocessed user",
            {
                "status": "planned",
                "hypothesis_id": hypothesis_id,
                "target_function_id": function_id,
                "binding_status": "bound",
                "experiment_binding": {
                    "hypothesis_id": hypothesis_id,
                    "observation_id": f"observation:{observation_id}",
                    "target_function_id": function_id,
                },
            },
        )
    )
    model.add_edge(Edge(invariant_id, "informs", hypothesis_id, {}))
    model.add_edge(Edge(f"observation:{observation_id}", "tests", hypothesis_id, {}))
    return model, CanonicalHypothesis(hypothesis.hypothesis_id, hypothesis.claim, 0.5), observation_id


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("backtest-artifacts/control-flow"))
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="cydra-venus-vulnerable-") as tmp:
        target = clone_target(Path(tmp) / "target")
        source = target / TARGET_PATH
        result = investigate(
            source,
            target=f"{TARGET_REPO}@{TARGET_REF}:{TARGET_PATH}",
            reasoning_surfaces=(generate_control_flow_hypotheses,),
            experiment_planner=plan_control_flow_experiment,
        )
        hypotheses = [
            h for h in result.hypotheses
            if h.invariant_id.startswith("INV-CONTROL-FLOW-")
        ]
        if len(hypotheses) != 1:
            raise SystemExit(f"expected one blind control-flow hypothesis, got {len(hypotheses)}")
        hypothesis = hypotheses[0]
        experiment = next(e for e in result.experiments if e.hypothesis_id == hypothesis.hypothesis_id)
        vulnerable = run_target(target, "vulnerable")

    with tempfile.TemporaryDirectory(prefix="cydra-venus-patched-") as tmp:
        target = clone_target(Path(tmp) / "target")
        patch_target(target)
        patched = run_target(target, "patched")

    with tempfile.TemporaryDirectory(prefix="cydra-venus-repro-v-") as tmp:
        target = clone_target(Path(tmp) / "target")
        independent_vulnerable = run_target(target, "independent-vulnerable")

    with tempfile.TemporaryDirectory(prefix="cydra-venus-repro-p-") as tmp:
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
        outcome_id="control-flow-differential",
    )

    reproduction_verified = (
        independent_vulnerable["status"] == "FAIL"
        and independent_patched["status"] == "PASS"
    )
    impact = ImpactAssessment(
        ImpactLevel.MEDIUM,
        "Prime score-update availability",
        "A reachable already-processed element can prevent updateScores from advancing, causing the transaction to exhaust its gas and preventing later users in the batch from receiving their score update.",
        ("at least one user in the supplied batch is already marked updated", "another user remains pending in the same batch"),
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
        finding_id=f"F-CONTROL-FLOW-{hypothesis.target_function}",
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
        "boundary": "actual pinned Venus repository and npm dependency graph executed; patched control changes only the loop-progress branch.",
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "result.json").write_text(
        json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, indent=2, default=str))
    return 0 if gate.decision.value == "READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
