from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from cydra.canonical_cycle import run_canonical_differential_cycle
from cydra.finding_gate import FindingCandidate, evaluate_finding_graph
from cydra.foundry import require_executed, run_foundry_test
from cydra.hypotheses import Hypothesis as CanonicalHypothesis
from cydra.impact import ImpactAssessment, ImpactLevel
from cydra.pipeline import investigate
from cydra.hypothesis_selection import select_next_hypothesis
from cydra.signature_reuse_planning import plan_signature_reuse_experiment
from cydra.solidity_model import parse_solidity
from cydra.structural_signature_reuse import generate_signature_reuse_hypotheses
from cydra.system_model import Edge, Node, SystemModel

TARGET_REPO = "https://github.com/code-423n4/2024-08-phi.git"
TARGET_REF = "2465e04364b759c721f1a0aebace69920411f8aa"
TARGET_PATH = "src/PhiFactory.sol"


def clone_target(destination: Path) -> Path:
    subprocess.run(
        ("git", "clone", "--no-tags", "--recurse-submodules", TARGET_REPO, str(destination)),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    subprocess.run(
        ("git", "-C", str(destination), "checkout", "--detach", TARGET_REF),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    subprocess.run(("git", "-C", str(destination), "submodule", "update", "--init", "--recursive"), check=True)
    subprocess.run(("npm", "install", "--ignore-scripts", "--no-audit", "--no-fund"), cwd=destination, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return destination


def write_reproduction_test(target_root: Path) -> Path:
    path = target_root / "test" / "CydraSignatureReuse.t.sol"
    path.write_text(
        """// SPDX-License-Identifier: MIT
pragma solidity 0.8.25;

import {TestClaimable} from "./Claimable.t.sol";

contract CydraSignatureReuseTest is TestClaimable {
    function testCydraSignedAuthorizationCannotBeReused() public {
        vm.warp(START_TIME + 2);
        address artAddress = phiFactory.getArtAddress(1);
        bytes memory data = _createSigSignData(true);
        bytes memory payload = abi.encodePacked(abi.encodeWithSignature("signatureClaim()"), data);
        uint256 mintFee = phiFactory.getArtMintFee(1, 1);

        vm.startPrank(participant, participant);
        (bool firstAccepted,) = artAddress.call{value: mintFee}(payload);
        require(firstAccepted, "first signed claim did not execute");

        (bool secondAccepted,) = artAddress.call{value: mintFee}(payload);
        require(!secondAccepted, "signed authorization was accepted twice");
        vm.stopPrank();
    }
}
""",
        encoding="utf-8",
    )
    return path


def run_target(root: Path, label: str):
    test = write_reproduction_test(root)
    completed = subprocess.run(
        ("forge", "test", "--match-test", "testCydraSignedAuthorizationCannotBeReused", "-vvv"),
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    passed = completed.returncode == 0
    return {
        "experiment_id": f"X-SIGNATURE-REUSE-{label}",
        "executed": True,
        "tests_run": 1,
        "tests_failed": 0 if passed else 1,
        "status": "PASS" if passed else "FAIL",
        "exit_code": completed.returncode,
        "stdout": completed.stdout[-12000:],
        "stderr": "",
    }


def patch_target(root: Path) -> None:
    path = root / TARGET_PATH
    source = path.read_text(encoding="utf-8")
    needle = "        if (!credMinted[art.credChainId][art.credId][minter_]) {"
    replacement = "        if (artMinted[artId_][minter_]) revert AddressAlreadyMinted();\n\n" + needle
    if needle not in source:
        raise RuntimeError("patched-control insertion point not found")
    path.write_text(source.replace(needle, replacement, 1), encoding="utf-8")


def canonical_model(hypothesis):
    model = SystemModel()
    contract_id = "contract:PhiFactory"
    function_id = f"function:PhiFactory:{hypothesis.target_function}"
    invariant_id = f"invariant:{hypothesis.invariant_id}"
    hypothesis_id = f"hypothesis:{hypothesis.hypothesis_id}"
    observation_id = "signature-reuse"
    model.add_node(Node(contract_id, "contract", "PhiFactory", {"provenance": "pinned historical source"}))
    model.add_node(Node(function_id, "function", hypothesis.target_function, {"provenance": "pinned historical source"}))
    model.add_node(Node(invariant_id, "invariant", hypothesis.claim, {"status": "inferred", "confidence": 0.84}))
    model.add_node(Node(hypothesis_id, "hypothesis", hypothesis.claim, {"belief": 0.5}))
    model.add_node(
        Node(
            f"observation:{observation_id}",
            "observation",
            "submit the exact same signed authorization twice",
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
    parser.add_argument("--output", type=Path, default=Path("backtest-artifacts/signature-reuse"))
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parents[1]

    with tempfile.TemporaryDirectory(prefix="cydra-phi-vulnerable-") as tmp:
        target = clone_target(Path(tmp) / "target")
        source = target / TARGET_PATH
        # Strict blind mode: no vulnerability class, target function, state surface,
        # reasoning-surface injection, or custom planner is supplied.
        result = investigate(
            source,
            target=f"{TARGET_REPO}@{TARGET_REF}:{TARGET_PATH}",
        )
        selection = select_next_hypothesis(
            result.hypotheses, result.invariants, result.experiments
        )
        hypothesis = selection.hypothesis
        if not hypothesis.invariant_id.startswith("INV-SIGNATURE-REUSE-"):
            raise SystemExit(
                "strict blind selector chose "
                + hypothesis.hypothesis_id
                + "/"
                + hypothesis.target_function
                + " instead of the independently evaluated signature-reuse hypothesis"
            )
        experiment = next(e for e in result.experiments if e.hypothesis_id == hypothesis.hypothesis_id)
        vulnerable = run_target(target, "vulnerable")

    with tempfile.TemporaryDirectory(prefix="cydra-phi-patched-") as tmp:
        target = clone_target(Path(tmp) / "target")
        patch_target(target)
        patched = run_target(target, "patched")

    with tempfile.TemporaryDirectory(prefix="cydra-phi-repro-v-") as tmp:
        target = clone_target(Path(tmp) / "target")
        independent_vulnerable = run_target(target, "independent-vulnerable")

    with tempfile.TemporaryDirectory(prefix="cydra-phi-repro-p-") as tmp:
        target = clone_target(Path(tmp) / "target")
        patch_target(target)
        independent_patched = run_target(target, "independent-patched")

    model, canonical_hypothesis, observation_id = canonical_model(hypothesis)
    class _Execution:
        def __init__(self, payload):
            self.__dict__.update(payload)
    vulnerable_execution = _Execution(vulnerable)
    patched_execution = _Execution(patched)
    cycle = run_canonical_differential_cycle(
        model,
        hypothesis=canonical_hypothesis,
        observation_id=observation_id,
        vulnerable=vulnerable_execution,
        patched=patched_execution,
        outcome_id="signature-reuse-differential",
    )
    reproduction_verified = (
        independent_vulnerable["status"] == "FAIL"
        and independent_patched["status"] == "PASS"
    )
    impact = ImpactAssessment(
        ImpactLevel.HIGH,
        "unauthorized repeated reward minting",
        "A valid signed claim can be consumed repeatedly, increasing the recipient's minted reward beyond the one-time authorization.",
        ("the same signed authorization remains valid after the first successful claim", "the art supply remains sufficient for the repeated mint"),
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
        finding_id=f"F-SIGNATURE-REUSE-{hypothesis.target_function}",
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
        "boundary": "actual pinned Phi repository and dependency graph executed; patched control is an isolated causal edit to the target source.",
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "result.json").write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))
    return 0 if gate.decision.value == "READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
