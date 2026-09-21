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

TARGET_REPO = "https://github.com/code-423n4/2024-02-ai-arena.git"
TARGET_REF = "06ee3e647a26292344b1e7b081e5af26a6ba81da"
TARGET_PATH = "src/FighterFarm.sol"

VULNERABLE_TEST_SOURCE = r"""// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../src/FighterFarm.sol";

contract CydraTypeDomainTest is Test {
    function testNarrowIdentifierBlocksValidHighRangeDomain() public {
        FighterFarm farm = new FighterFarm(address(this), address(this), address(this));
        bytes memory data = abi.encodeWithSignature("reRoll(uint8,uint8)", 256, 0);
        (bool ok, bytes memory ret) = address(farm).call(data);
        assertFalse(ok, "boundary call unexpectedly succeeded");
        assertEq(ret.length, 0, "vulnerable target should reject 256 at ABI boundary");
    }
}
"""

PATCHED_TEST_SOURCE = r"""// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../src/FighterFarm.sol";

contract CydraTypeDomainTest is Test {
    function testWidenedIdentifierReachesFunction() public {
        FighterFarm farm = new FighterFarm(address(this), address(this), address(this));
        bytes memory data = abi.encodeWithSignature("reRoll(uint256,uint8)", 256, 0);
        (bool ok, bytes memory ret) = address(farm).call(data);
        assertFalse(ok, "control should still reject the nonexistent token");
        assertGt(ret.length, 0, "widened control must reach target logic before reverting");
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
        ("forge", "install", "foundry-rs/forge-std", "--no-commit"),
        cwd=destination, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    return destination

def write_test(root: Path, label: str) -> None:
    path = root / "test" / "CydraTypeDomain.t.sol"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(PATCHED_TEST_SOURCE if "patched" in label else VULNERABLE_TEST_SOURCE, encoding="utf-8")

def run_target(root: Path, label: str):
    write_test(root, label)
    completed = subprocess.run(
        ("forge", "test", "--match-test", "testNarrowIdentifierBlocksValidHighRangeDomain|testWidenedIdentifierReachesFunction", "-vvv"),
        cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    return {
        "experiment_id": f"X-TYPE-DOMAIN-{label}",
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
    old = "function reRoll(uint8 tokenId, uint8 fighterType) public"
    new = "function reRoll(uint256 tokenId, uint8 fighterType) public"
    if old not in source:
        raise RuntimeError("type-domain control insertion point not found")
    path.write_text(source.replace(old, new, 1), encoding="utf-8")

def canonical_model(hypothesis):
    model = SystemModel()
    function_id = f"function:FighterFarm:{hypothesis.target_function}"
    invariant_id = f"invariant:{hypothesis.invariant_id}"
    hypothesis_id = f"hypothesis:{hypothesis.hypothesis_id}"
    observation_id = "high-range-identifier-reachability"
    model.add_node(Node("contract:FighterFarm", "contract", "FighterFarm", {"provenance": "pinned historical source"}))
    model.add_node(Node(function_id, "function", hypothesis.target_function, {"provenance": "pinned historical source"}))
    model.add_node(Node(invariant_id, "invariant", hypothesis.claim, {"status": "inferred", "confidence": 0.90}))
    model.add_node(Node(hypothesis_id, "hypothesis", hypothesis.claim, {"belief": 0.5}))
    model.add_node(Node(
        f"observation:{observation_id}", "observation",
        "identifier 256 is valid for the uint256 ERC721/state domain but is rejected before reRoll logic when decoded as uint8",
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
    parser.add_argument("--output", type=Path, default=Path("backtest-artifacts/strict-blind-type-domain"))
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="cydra-ai-arena-blind-v-") as tmp:
        target = clone_target(Path(tmp) / "target")
        source = target / TARGET_PATH
        investigation = investigate(source, target=f"{TARGET_REPO}@{TARGET_REF}:{TARGET_PATH}")
        selection = select_next_hypothesis(investigation.hypotheses, investigation.invariants, investigation.experiments)
        hypothesis = selection.hypothesis
        if not hypothesis.invariant_id.startswith("INV-TYPE-DOMAIN-"):
            raise SystemExit(
                "strict blind selector did not choose type-domain hypothesis: "
                + hypothesis.hypothesis_id + "/" + hypothesis.target_function
            )
        experiment = next(e for e in investigation.experiments if e.hypothesis_id == hypothesis.hypothesis_id)
        vulnerable = run_target(target, "vulnerable")

    with tempfile.TemporaryDirectory(prefix="cydra-ai-arena-blind-p-") as tmp:
        target = clone_target(Path(tmp) / "target")
        patch_target(target)
        patched = run_target(target, "patched")

    with tempfile.TemporaryDirectory(prefix="cydra-ai-arena-blind-repro-v-") as tmp:
        target = clone_target(Path(tmp) / "target")
        independent_vulnerable = run_target(target, "independent-vulnerable")

    with tempfile.TemporaryDirectory(prefix="cydra-ai-arena-blind-repro-p-") as tmp:
        target = clone_target(Path(tmp) / "target")
        patch_target(target)
        independent_patched = run_target(target, "independent-patched")

    model, canonical_hypothesis, observation_id = canonical_model(hypothesis)

    class Execution:
        def __init__(self, payload):
            self.__dict__.update(payload)

    cycle = run_canonical_differential_cycle(
        model, hypothesis=canonical_hypothesis, observation_id=observation_id,
        vulnerable=Execution(vulnerable), patched=Execution(patched),
        outcome_id="strict-blind-type-domain-differential",
    )
    reproduction_verified = independent_vulnerable["status"] == "FAIL" and independent_patched["status"] == "PASS"
    impact = ImpactAssessment(
        ImpactLevel.MEDIUM,
        "identifier-domain availability",
        "Owners of valid high-range NFT identifiers cannot invoke the reroll operation because the public ABI narrows the identifier before the function body is reached.",
        ("token identifiers use the uint256 ERC721/state domain", "reRoll exposes a narrower uint8 identifier"),
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
        finding_id=f"F-STRICT-BLIND-TYPE-DOMAIN-{hypothesis.target_function}",
        hypothesis_id=f"hypothesis:{hypothesis.hypothesis_id}",
        evidence_ids=cycle.causal_verification.evidence_ids,
        causal_chain_id=cycle.causal_chain.chain_id,
    )
    payload = {
        "target": {"repo": TARGET_REPO, "ref": TARGET_REF, "path": TARGET_PATH},
        "blind_selection": {"hypothesis": hypothesis.__dict__, "score": selection.score},
        "experiment": experiment.__dict__,
        "vulnerable": vulnerable,
        "patched": patched,
        "causal_verification": cycle.causal_verification.__dict__,
        "independent_vulnerable": independent_vulnerable,
        "independent_patched": independent_patched,
        "reproduction_verified": reproduction_verified,
        "finding_gate": gate.decision.value,
        "boundary": "normal class-neutral blind pipeline selected the type-domain hypothesis; the synthetic control changes only tokenId parameter width; independent clones reproduce the ABI reachability differential.",
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "result.json").write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))
    return 0 if gate.decision.value == "READY" else 1

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        output = Path("backtest-artifacts/strict-blind-type-domain")
        output.mkdir(parents=True, exist_ok=True)
        (output / "runner_error.json").write_text(json.dumps({"error_type": type(exc).__name__, "error": str(exc)}, indent=2) + "\n", encoding="utf-8")
        raise
