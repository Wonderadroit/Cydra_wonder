from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from cydra.canonical_cycle import run_canonical_differential_cycle
from cydra.finding_gate import FindingCandidate, evaluate_finding_graph
from cydra.hypotheses import Hypothesis as ModelHypothesis
from cydra.hypothesis_selection import select_next_hypothesis
from cydra.impact import ImpactAssessment, ImpactLevel
from cydra.pipeline import investigate
from cydra.system_model import Edge, Node, SystemModel

TARGET_PATH = Path("benchmarks/037_keeper_zero_work_incentive/Target.sol")

HARNESS = """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../Target.sol";

interface IKeeperLike {
    function settle(
        bytes32[] calldata ids,
        address[] calldata markets,
        uint256[] calldata versions,
        uint256[] calldata maxCounts
    ) external;
}

contract C is Test {
    function test() public {
        vm.deal(address(this), 5 ether);

        KeeperLike target = new KeeperLike{value: 5 ether}();
        uint256 initialBalance = address(this).balance;
        bytes32[] memory ids = new bytes32[](0);
        address[] memory markets = new address[](0);
        uint256[] memory versions = new uint256[](0);
        uint256[] memory maxCounts = new uint256[](0);

        (bool ok,) = address(target).call(
            abi.encodeWithSelector(
                IKeeperLike.settle.selector,
                ids,
                markets,
                versions,
                maxCounts
            )
        );

        require(!ok || address(this).balance <= initialBalance, "reward paid for zero work");
    }

    receive() external payable {}
}
"""


def setup(dest: Path) -> Path:
    subprocess.run(
        ("forge", "init", "--force", str(dest)),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    subprocess.run(
        ("forge", "install", "foundry-rs/forge-std", "--no-commit"),
        cwd=dest,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    (dest / "Target.sol").write_text(TARGET_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    (dest / "test").mkdir(exist_ok=True)
    return dest


def run_fixture(patched: bool, label: str):
    with tempfile.TemporaryDirectory(prefix="cydra-037-") as t:
        root = setup(Path(t) / "project")
        source = HARNESS.replace(
            "KeeperLike target = new KeeperLike{value: 5 ether}();",
            "KeeperLikePatched target = new KeeperLikePatched{value: 5 ether}();",
        ) if patched else HARNESS
        (root / "test" / "Keeper.t.sol").write_text(source, encoding="utf-8")
        process = subprocess.run(
            ("forge", "test", "--match-test", "test", "-vvv"),
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        return {
            "experiment_id": "X-" + label,
            "executed": True,
            "tests_run": 1,
            "tests_failed": 0 if process.returncode == 0 else 1,
            "status": "PASS" if process.returncode == 0 else "FAIL",
            "security_assertion_triggered": "reward paid for zero work" in process.stdout,
            "exit_code": process.returncode,
            "stdout": process.stdout[-12000:],
            "stderr": "",
        }


def canonical_model(h):
    model = SystemModel()
    invariant_id = "invariant:" + h.invariant_id
    hypothesis_id = "hypothesis:" + h.hypothesis_id
    observation_id = "keeper-zero-work"

    model.add_node(Node(
        "contract:KeeperLike",
        "contract",
        "KeeperLike",
        {"provenance": "historical-style Perennial keeper reduction"},
    ))
    model.add_node(Node(
        "contract:KeeperLikePatched",
        "contract",
        "KeeperLikePatched",
        {"provenance": "causal control"},
    ))
    model.add_node(Node(
        "function:KeeperLike:" + h.target_function,
        "function",
        h.target_function,
        {},
    ))
    model.add_node(Node(
        invariant_id,
        "invariant",
        h.claim,
        {"status": "inferred", "confidence": 0.72},
    ))
    model.add_node(Node(hypothesis_id, "hypothesis", h.claim, {"belief": 0.5}))
    model.add_node(Node(
        "observation:" + observation_id,
        "observation",
        "reward versus executed work",
        {
            "status": "planned",
            "hypothesis_id": hypothesis_id,
            "target_function_id": "function:KeeperLike:" + h.target_function,
            "binding_status": "bound",
            "experiment_binding": {
                "hypothesis_id": hypothesis_id,
                "observation_id": "observation:" + observation_id,
                "target_function_id": "function:KeeperLike:" + h.target_function,
            },
        },
    ))
    model.add_edge(Edge(invariant_id, "informs", hypothesis_id, {}))
    model.add_edge(Edge("observation:" + observation_id, "tests", hypothesis_id, {}))
    return model, ModelHypothesis("hypothesis:" + h.hypothesis_id, h.claim, 0.5), observation_id


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("backtest-artifacts/benchmark-037-keeper-zero-work-incentive"),
    )
    args = parser.parse_args()

    investigation = investigate(
        TARGET_PATH,
        target="benchmark-037-keeper-zero-work-incentive",
    )
    selection = select_next_hypothesis(
        investigation.hypotheses,
        investigation.invariants,
        investigation.experiments,
    )
    hypothesis = selection.hypothesis
    if hypothesis.invariant_id != "INV-INCENTIVE-LIVENESS-settle":
        raise SystemExit(
            "strict blind selector did not choose incentive-liveness hypothesis: "
            + hypothesis.hypothesis_id
        )

    experiment = next(
        item for item in investigation.experiments
        if item.hypothesis_id == hypothesis.hypothesis_id
    )

    vulnerable = run_fixture(False, "blind-vulnerable")
    patched = run_fixture(True, "patched")
    independent_vulnerable = run_fixture(False, "independent-vulnerable")
    independent_patched = run_fixture(True, "independent-patched")

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
        outcome_id="benchmark-037-incentive-differential",
    )

    reproduction = (
        vulnerable["status"] == "FAIL"
        and vulnerable["security_assertion_triggered"]
        and patched["status"] == "PASS"
        and independent_vulnerable["status"] == "FAIL"
        and independent_vulnerable["security_assertion_triggered"]
        and independent_patched["status"] == "PASS"
    )
    impact = ImpactAssessment(
        ImpactLevel.MEDIUM,
        "keeper incentive pool",
        "A permissionless caller can receive a keeper reward without performing any qualifying work.",
        (
            "the rewarded function accepts empty work arrays",
            "the reward-bearing modifier pays after the function returns",
        ),
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
            reproduction,
        ),
        finding_id="F-BENCHMARK-037-" + hypothesis.target_function,
        hypothesis_id="hypothesis:" + hypothesis.hypothesis_id,
        evidence_ids=cycle.causal_verification.evidence_ids,
        causal_chain_id=cycle.causal_chain.chain_id,
    )

    payload = {
        "historical_reference": "Sherlock 2023-10 Perennial issue #50; executable reduction only",
        "blind_selection": {
            "hypothesis": hypothesis.__dict__,
            "score": selection.score,
        },
        "experiment": experiment.__dict__,
        "vulnerable": vulnerable,
        "patched": patched,
        "causal_verification": cycle.causal_verification.__dict__,
        "independent_vulnerable": independent_vulnerable,
        "independent_patched": independent_patched,
        "reproduction_verified": reproduction,
        "finding_gate": gate.decision.value,
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "result.json").write_text(
        json.dumps(payload, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, default=str))
    return 0 if gate.decision.value == "READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
