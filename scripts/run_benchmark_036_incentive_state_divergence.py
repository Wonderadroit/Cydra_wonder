from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from cydra.canonical_cycle import run_canonical_differential_cycle
from cydra.finding_gate import FindingCandidate, evaluate_finding_graph
from cydra.hypothesis_selection import select_next_hypothesis
from cydra.impact import ImpactAssessment, ImpactLevel
from cydra.models import Hypothesis as ModelHypothesis
from cydra.pipeline import investigate
from cydra.system_model import Edge, Node, SystemModel

TARGET_PATH = Path("benchmarks/036_incentive_state_divergence/Target.sol")


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
    with tempfile.TemporaryDirectory(prefix="cydra-036-") as t:
        root = setup(Path(t) / "project")
        target_type = "IncentiveQueuePatched" if patched else "IncentiveQueue"
        constructor_funding = "5 ether" if patched else "2 ether"
        request = (
            '(bool a,) = address(target).call{value: 2 ether}'
            '(abi.encodeWithSignature("requestWork()"));'
            if patched
            else '(bool a,) = address(target).call(abi.encodeWithSignature("requestWork()"));'
        )
        harness = f"""// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../Target.sol";

contract C is Test {{
    function test() public {{
        vm.deal(address(this), 2 ether);
        {target_type} target = new {target_type}{{value: {constructor_funding}}}();
        uint256 initialBalance = address(this).balance;
        {request}
        require(a, "request failed");

        (bool c,) = address(target).call(abi.encodeWithSignature("commitWork()"));
        require(c, "commit failed");

        // The security property is net extraction: a caller should not finish
        // with more value than it started with after manufacturing the work.
        require(
            address(this).balance <= initialBalance,
            "caller extracted more reward than the request cost"
        );
    }}

    receive() external payable {{}}
}}
"""
        (root / "test" / "Incentive.t.sol").write_text(harness, encoding="utf-8")
        p = subprocess.run(
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
            "tests_failed": 0 if p.returncode == 0 else 1,
            "status": "PASS" if p.returncode == 0 else "FAIL",
            "exit_code": p.returncode,
            "stdout": p.stdout[-12000:],
            "stderr": "",
        }


def canonical_model(h):
    model = SystemModel()
    invariant_id = "invariant:" + h.invariant_id
    hypothesis_id = "hypothesis:" + h.hypothesis_id
    observation_id = "incentive-cost-reward-gap"

    model.add_node(
        Node(
            "contract:IncentiveQueue",
            "contract",
            "IncentiveQueue",
            {"provenance": "historical-style incentive fixture"},
        )
    )
    model.add_node(
        Node(
            "contract:IncentiveQueuePatched",
            "contract",
            "IncentiveQueuePatched",
            {"provenance": "causal control"},
        )
    )
    model.add_node(
        Node(
            "function:IncentiveQueue:" + h.target_function,
            "function",
            h.target_function,
            {},
        )
    )
    model.add_node(
        Node(
            invariant_id,
            "invariant",
            h.claim,
            {"status": "inferred", "confidence": 0.72},
        )
    )
    model.add_node(
        Node(
            hypothesis_id,
            "hypothesis",
            h.claim,
            {"belief": 0.5},
        )
    )
    model.add_node(
        Node(
            "observation:" + observation_id,
            "observation",
            "caller cost versus payout reward",
            {
                "status": "planned",
                "hypothesis_id": hypothesis_id,
                "target_function_id": "function:IncentiveQueue:" + h.target_function,
                "binding_status": "bound",
                "experiment_binding": {
                    "hypothesis_id": hypothesis_id,
                    "observation_id": "observation:" + observation_id,
                    "target_function_id": "function:IncentiveQueue:" + h.target_function,
                },
            },
        )
    )
    model.add_edge(Edge(invariant_id, "informs", hypothesis_id, {}))
    model.add_edge(Edge("observation:" + observation_id, "tests", hypothesis_id, {}))
    return model, ModelHypothesis(h.hypothesis_id, h.claim, 0.5), observation_id


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("backtest-artifacts/benchmark-036-incentive-state-divergence"),
    )
    args = parser.parse_args()

    investigation = investigate(
        TARGET_PATH,
        target="benchmark-036-incentive-state-divergence",
    )
    selection = select_next_hypothesis(
        investigation.hypotheses,
        investigation.invariants,
        investigation.experiments,
    )
    hypothesis = selection.hypothesis

    if hypothesis.invariant_id != "INV-INCENTIVE-LIVENESS-commitWork":
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
        outcome_id="benchmark-036-incentive-differential",
    )

    reproduction = (
        independent_vulnerable["status"] == "FAIL"
        and independent_patched["status"] == "PASS"
    )

    impact = ImpactAssessment(
        ImpactLevel.MEDIUM,
        "incentive extraction",
        "A permissionless caller can manufacture payout-eligible work without bearing "
        "the intended request cost and capture protocol-funded incentives.",
        (
            "requestWork creates work without value transfer",
            "commitWork pays a fixed reward to msg.sender",
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
        finding_id="F-BENCHMARK-036-" + hypothesis.target_function,
        hypothesis_id="hypothesis:" + hypothesis.hypothesis_id,
        evidence_ids=cycle.causal_verification.evidence_ids,
        causal_chain_id=cycle.causal_chain.chain_id,
    )

    payload = {
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
