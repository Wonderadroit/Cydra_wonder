from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from cydra.canonical_cycle import run_canonical_differential_cycle
from cydra.finding_gate import FindingCandidate, evaluate_finding_graph
from cydra.hypothesis_selection import select_next_hypothesis
from cydra.hypotheses import Hypothesis as CanonicalHypothesis
from cydra.impact import ImpactAssessment, ImpactLevel
from cydra.pipeline import investigate
from cydra.system_model import Edge, Node, SystemModel

TARGET_REPO = "https://github.com/code-423n4/2025-05-blackhole.git"
TARGET_REF = "92fff849d3b266e609e6d63478c4164d9f608e91"
TARGET_PATH = "contracts/GenesisPoolManager.sol"

TEST_SOURCE = r"""// SPDX-License-Identifier: MIT
pragma solidity 0.8.13;

import "forge-std/Test.sol";
import {GenesisPoolManager} from "contracts/GenesisPoolManager.sol";

contract CydraGuardProgressTest is Test {
    function testOwnerCanSetNonZeroRouter() public {
        GenesisPoolManager manager = new GenesisPoolManager();
        manager.initialize(
            address(0x1001),
            address(0x1002),
            address(0x1003),
            address(0x1004),
            address(0x1005),
            address(0x1006),
            address(0x1007),
            address(0x1008)
        );

        address desiredRouter = address(0xBEEF);
        manager.setRouter(desiredRouter);
        assertEq(manager.router(), desiredRouter, "owner should be able to set a valid router");
    }
}
"""


def clone_target(destination: Path) -> Path:
    completed = subprocess.run(
        ("git", "clone", "--no-tags", "--recurse-submodules", TARGET_REPO, str(destination)),
        check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError("target clone failed:\n" + completed.stdout[-12000:])
    subprocess.run(
        ("git", "-C", str(destination), "checkout", "--detach", TARGET_REF),
        check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    subprocess.run(
        ("git", "-C", str(destination), "submodule", "update", "--init", "--recursive"),
        check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    return destination


def write_harness(root: Path) -> None:
    path = root / "test" / "autogen" / "CydraGuardProgress.t.sol"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(TEST_SOURCE, encoding="utf-8")


def run_target(root: Path, label: str) -> dict:
    write_harness(root)
    completed = subprocess.run(
        (
            "forge", "test", "--match-path", "test/autogen/CydraGuardProgress.t.sol",
            "--match-test", "testOwnerCanSetNonZeroRouter", "-vvv",
        ),
        cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    return {
        "experiment_id": f"X-OPEN-GUARD-{label}",
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
    old = 'require(_router == address(0), "ZA");'
    new = 'require(_router != address(0), "ZA");'
    if old not in source:
        raise RuntimeError("guard causal insertion point not found")
    path.write_text(source.replace(old, new, 1), encoding="utf-8")


def canonical_model(hypothesis):
    model = SystemModel()
    contract_id = "contract:GenesisPoolManager"
    function_id = f"function:GenesisPoolManager:{hypothesis.target_function}"
    invariant_id = f"invariant:{hypothesis.invariant_id}"
    hypothesis_id = f"hypothesis:{hypothesis.hypothesis_id}"
    observation_id = "valid-router-rejected"

    model.add_node(Node(contract_id, "contract", "GenesisPoolManager",
                        {"provenance": "pinned historical source"}))
    model.add_node(Node(function_id, "function", hypothesis.target_function,
                        {"provenance": "pinned historical source"}))
    model.add_node(Node(invariant_id, "invariant", hypothesis.claim,
                        {"status": "inferred", "confidence": 0.9}))
    model.add_node(Node(hypothesis_id, "hypothesis", hypothesis.claim, {"belief": 0.5}))
    model.add_node(Node(
        f"observation:{observation_id}", "observation",
        "a non-zero router update is rejected by the owner-only setter",
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
    ))
    model.add_edge(Edge(invariant_id, "informs", hypothesis_id, {}))
    model.add_edge(Edge(f"observation:{observation_id}", "tests", hypothesis_id, {}))
    return model, CanonicalHypothesis(hypothesis.hypothesis_id, hypothesis.claim, 0.5), observation_id


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("backtest-artifacts/open-ended-guard"))
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="cydra-blackhole-vulnerable-") as tmp:
        target = clone_target(Path(tmp) / "target")
        source = target / TARGET_PATH

        # No vulnerability class, target function, state surface, or historical
        # answer is supplied to CYDRA. The benchmark oracle is used only after
        # blind selection, to evaluate the selected hypothesis.
        result = investigate(source, target=f"{TARGET_REPO}@{TARGET_REF}:{TARGET_PATH}")
        selection = select_next_hypothesis(
            result.hypotheses, result.invariants, result.experiments
        )
        hypothesis = selection.hypothesis
        experiment = next(
            e for e in result.experiments if e.hypothesis_id == hypothesis.hypothesis_id
        )

        if hypothesis.target_function != "setRouter":
            raise RuntimeError(
                "blind selector did not choose the historical guard target: "
                + hypothesis.hypothesis_id
                + " / "
                + hypothesis.target_function
            )
        vulnerable = run_target(target, "vulnerable")

    with tempfile.TemporaryDirectory(prefix="cydra-blackhole-patched-") as tmp:
        target = clone_target(Path(tmp) / "target")
        patch_target(target)
        patched = run_target(target, "patched")

    with tempfile.TemporaryDirectory(prefix="cydra-blackhole-repro-v-") as tmp:
        target = clone_target(Path(tmp) / "target")
        independent_vulnerable = run_target(target, "independent-vulnerable")

    with tempfile.TemporaryDirectory(prefix="cydra-blackhole-repro-p-") as tmp:
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
        outcome_id="open-ended-guard-differential",
    )

    reproduction_verified = (
        independent_vulnerable["status"] == "FAIL"
        and independent_patched["status"] == "PASS"
    )
    impact = ImpactAssessment(
        ImpactLevel.MEDIUM,
        "Administrative router configuration integrity",
        "The owner-only router setter rejects valid non-zero router addresses, preventing the intended configuration transition and leaving the existing router unchanged.",
        ("the owner must be able to configure a valid router", "the setter must not reject every valid non-zero address"),
        cycle.causal_verification.evidence_ids,
    )
    gate = evaluate_finding_graph(
        model,
        candidate=FindingCandidate(
            True, False, True, True,
            cycle.causal_verification.state.value == "verified",
            impact.assessed, reproduction_verified,
        ),
        finding_id=f"F-OPEN-GUARD-{hypothesis.target_function}",
        hypothesis_id=f"hypothesis:{hypothesis.hypothesis_id}",
        evidence_ids=cycle.causal_verification.evidence_ids,
        causal_chain_id=cycle.causal_chain.chain_id,
    )

    payload = {
        "historical_target": {"repo": TARGET_REPO, "ref": TARGET_REF, "path": TARGET_PATH},
        "blind_selection": {
            "hypothesis_id": hypothesis.hypothesis_id,
            "target_function": hypothesis.target_function,
            "score": selection.score,
            "candidate_count": len(result.hypotheses),
        },
        "hypothesis": hypothesis.__dict__,
        "experiment": experiment.__dict__,
        "vulnerable": vulnerable,
        "patched": patched,
        "causal_verification": cycle.causal_verification.__dict__,
        "independent_vulnerable": independent_vulnerable,
        "independent_patched": independent_patched,
        "reproduction_verified": reproduction_verified,
        "finding_gate": gate.decision.value,
        "boundary": "actual pinned Blackhole repository and dependency graph executed; causal control changes only the inverted router-address guard.",
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "result.json").write_text(
        json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, indent=2, default=str))
    return 0 if gate.decision.value == "READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
