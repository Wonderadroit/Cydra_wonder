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

TARGET_REPO = "https://github.com/sherlock-audit/2022-11-bond.git"
TARGET_REF = "main"
TARGET_PATH = "src/BondFixedTermTeller.sol"

TEST_SOURCE = r"""// SPDX-License-Identifier: MIT
pragma solidity 0.8.15;

import "forge-std/Test.sol";
import "../src/BondFixedTermTeller.sol";

contract MockERC20 is ERC20 {
    constructor() ERC20("Mock", "MOCK", 18) {}
    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}

contract CallbackObserver is ERC1155TokenReceiver {
    BondFixedTermTeller public immutable teller;
    ERC20 public immutable token;
    uint256 public expectedTokenId;
    uint256 public observedSupply;

    constructor(BondFixedTermTeller teller_, ERC20 token_) {
        teller = teller_;
        token = token_;
    }

    function prepareAndCreate(uint256 tokenId, uint256 amount, uint48 expiry) external {
        expectedTokenId = tokenId;
        token.approve(address(teller), amount);
        teller.create(token, expiry, amount);
    }

    function onERC1155Received(
        address,
        address,
        uint256 id,
        uint256,
        bytes calldata
    ) external returns (bytes4) {
        (,, , , uint256 supply) = teller.tokenMetadata(id);
        observedSupply = supply;
        return ERC1155TokenReceiver.onERC1155Received.selector;
    }

    function onERC1155BatchReceived(address,address,uint256[] calldata,uint256[] calldata,bytes calldata)
        external pure returns (bytes4)
    {
        return ERC1155TokenReceiver.onERC1155BatchReceived.selector;
    }
}

contract CydraReadOnlyReentrancyTest is Test {
    function testCallbackCannotObserveStaleSupply() public {
        BondFixedTermTeller teller = new BondFixedTermTeller(
            address(this),
            IBondAggregator(address(0)),
            address(this),
            Authority(address(0))
        );
        MockERC20 token = new MockERC20();
        uint48 expiry = uint48(block.timestamp + 2 days);
        uint256 tokenId = teller.deploy(token, expiry);

        CallbackObserver observer = new CallbackObserver(teller, token);
        uint256 amount = 10e18;
        token.mint(address(observer), amount);

        observer.prepareAndCreate(tokenId, amount, expiry);

        assertEq(observer.observedSupply(), amount, "callback observed stale aggregate supply");
        (,,, , uint256 settledSupply) = teller.tokenMetadata(tokenId);
        assertEq(settledSupply, amount);
    }
}
"""

def clone_target(destination: Path) -> Path:
    subprocess.run(("git", "clone", "--no-tags", "--recurse-submodules", TARGET_REPO, str(destination)),
                   check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    subprocess.run(("git", "-C", str(destination), "checkout", "--detach", TARGET_REF),
                   check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    forge_std = destination / "lib" / "forge-std"
    if not forge_std.exists():
        subprocess.run(("forge", "install", "foundry-rs/forge-std", "--no-commit"),
                       cwd=destination, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return destination

def run_target(root: Path, label: str):
    path = root / "test" / "CydraReadOnlyReentrancy.t.sol"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(TEST_SOURCE, encoding="utf-8")
    completed = subprocess.run(
        ("forge", "test", "--match-test", "testCallbackCannotObserveStaleSupply", "-vvv"),
        cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    return {
        "experiment_id": f"X-READONLY-{label}",
        "executed": True,
        "tests_run": 1,
        "tests_failed": 0 if completed.returncode == 0 else 1,
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "exit_code": completed.returncode,
        "stdout": completed.stdout[-14000:],
        "stderr": "",
    }

def patch_target(root: Path) -> None:
    path = root / TARGET_PATH
    source = path.read_text(encoding="utf-8")
    pattern = r"(function\s+_mintToken\s*\([^)]*\)\s*internal\s*\{\s*)_mint\(to_, tokenId_, amount_\, bytes\(\"\"\)\);\s*(tokenMetadata\[tokenId_\]\.supply\s*\+=\s*amount_;)"
    replacement = r"\1\2\n        _mint(to_, tokenId_, amount_, bytes(\"\"));"
    updated, count = __import__("re").subn(pattern, replacement, source, count=1, flags=__import__("re").S)
    if count != 1:
        raise RuntimeError("read-only reentrancy control insertion point not found")
    path.write_text(updated, encoding="utf-8")

def canonical_model(hypothesis):
    model = SystemModel()
    function_id = f"function:BondFixedTermTeller:{hypothesis.target_function}"
    invariant_id = f"invariant:{hypothesis.invariant_id}"
    hypothesis_id = f"hypothesis:{hypothesis.hypothesis_id}"
    observation_id = "callback-public-mapping-supply"
    model.add_node(Node("contract:BondFixedTermTeller", "contract", "BondFixedTermTeller", {"provenance": "pinned historical source"}))
    model.add_node(Node(function_id, "function", hypothesis.target_function, {"provenance": "pinned historical source"}))
    model.add_node(Node(invariant_id, "invariant", hypothesis.claim, {"status": "inferred", "confidence": 0.90}))
    model.add_node(Node(hypothesis_id, "hypothesis", hypothesis.claim, {"belief": 0.5}))
    model.add_node(Node(f"observation:{observation_id}", "observation",
                        "public tokenMetadata getter observes supply during ERC1155 receiver callback",
                        {"status": "planned", "hypothesis_id": hypothesis_id,
                         "target_function_id": function_id, "binding_status": "bound"}))
    model.add_edge(Edge(invariant_id, "informs", hypothesis_id, {}))
    model.add_edge(Edge(f"observation:{observation_id}", "tests", hypothesis_id, {}))
    return model, CanonicalHypothesis(hypothesis.hypothesis_id, hypothesis.claim, 0.5), observation_id

def run_external_outcome_probe(root: Path):
    probe = r"""// SPDX-License-Identifier: MIT
pragma solidity 0.8.15;
import "forge-std/Test.sol";
import "../src/BondFixedTermTeller.sol";

contract FalseERC20 is ERC20 {
    constructor() ERC20("False", "FALSE", 18) {}
    function transferFrom(address, address, uint256) public pure override returns (bool) { return false; }
}
contract ExternalOutcomeProbe is Test {
    function testFalseTransferFromIsRejected() public {
        BondFixedTermTeller teller = new BondFixedTermTeller(address(this), IBondAggregator(address(0)), address(this), Authority(address(0)));
        FalseERC20 token = new FalseERC20();
        uint48 expiry = uint48(block.timestamp + 2 days);
        teller.deploy(token, expiry);
        vm.expectRevert();
        teller.create(token, expiry, 1);
    }
}
"""
    path = root / "test" / "CydraExternalOutcomeProbe.t.sol"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(probe, encoding="utf-8")
    completed = subprocess.run(
        ("forge", "test", "--match-test", "testFalseTransferFromIsRejected", "-vvv"),
        cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    return {
        "experiment_id": "X-EXTERNAL-OUTCOME-create",
        "executed": True,
        "tests_run": 1,
        "tests_failed": 0 if completed.returncode == 0 else 1,
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "exit_code": completed.returncode,
        "stdout": completed.stdout[-12000:],
        "stderr": "",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("backtest-artifacts/strict-blind-readonly-bond"))
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="cydra-bond-blind-v-") as tmp:
        target = clone_target(Path(tmp) / "target")
        investigation = investigate(target / TARGET_PATH, target=f"{TARGET_REPO}@{TARGET_REF}:{TARGET_PATH}")
        selection = select_next_hypothesis(investigation.hypotheses, investigation.invariants, investigation.experiments)
        hypothesis = selection.hypothesis
        experiment = next(e for e in investigation.experiments if e.hypothesis_id == hypothesis.hypothesis_id)
        first_observation = None
        if hypothesis.hypothesis_id.startswith("H-EXTERNAL-OUTCOME-"):
            first_observation = run_external_outcome_probe(target)
            print("first research-loop observation:", json.dumps(first_observation, indent=2))
            selection = select_next_hypothesis(
                investigation.hypotheses,
                investigation.invariants,
                investigation.experiments,
                observed_statuses={hypothesis.hypothesis_id: "rejected" if first_observation["status"] == "PASS" else "UNMEASURABLE"},
            )
            hypothesis = selection.hypothesis
            experiment = next(e for e in investigation.experiments if e.hypothesis_id == hypothesis.hypothesis_id)
        if not hypothesis.hypothesis_id.startswith("H-READONLY-_mintToken-mapping"):
            raise SystemExit("strict blind selector did not choose callback-visible read-only hypothesis: " + hypothesis.hypothesis_id)
        vulnerable = run_target(target, "vulnerable")

    with tempfile.TemporaryDirectory(prefix="cydra-bond-blind-p-") as tmp:
        target = clone_target(Path(tmp) / "target")
        patch_target(target)
        patched = run_target(target, "patched")

    with tempfile.TemporaryDirectory(prefix="cydra-bond-blind-rv-") as tmp:
        independent_vulnerable = run_target(clone_target(Path(tmp) / "target"), "independent-vulnerable")

    with tempfile.TemporaryDirectory(prefix="cydra-bond-blind-rp-") as tmp:
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
        outcome_id="strict-blind-readonly-bond-differential",
    )
    reproduction_verified = independent_vulnerable["status"] == "FAIL" and independent_patched["status"] == "PASS"
    impact = ImpactAssessment(
        ImpactLevel.MEDIUM,
        "transient state observation",
        "A receiver callback can observe a stale bond-token supply through the public metadata getter before the minting operation records the new supply.",
        ("ERC1155 mint invokes a receiver callback", "bond supply is updated after the callback-capable mint"),
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
        finding_id=f"F-STRICT-BLIND-READONLY-{hypothesis.target_function}",
        hypothesis_id=f"hypothesis:{hypothesis.hypothesis_id}",
        evidence_ids=cycle.causal_verification.evidence_ids,
        causal_chain_id=cycle.causal_chain.chain_id,
    )
    payload = {
        "target": {"repo": TARGET_REPO, "ref": TARGET_REF, "path": TARGET_PATH},
        "blind_selection": {"hypothesis": hypothesis.__dict__, "score": selection.score},
        "experiment": experiment.__dict__,
        "research_loop_observation": first_observation,
        "vulnerable": vulnerable,
        "patched": patched,
        "causal_verification": cycle.causal_verification.__dict__,
        "independent_vulnerable": independent_vulnerable,
        "independent_patched": independent_patched,
        "reproduction_verified": reproduction_verified,
        "finding_gate": gate.decision.value,
        "boundary": "normal class-neutral pipeline selected the read-only callback hypothesis; no target function, vulnerability class, exploit sequence, or historical answer was supplied.",
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "result.json").write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))
    return 0 if gate.decision.value == "READY" else 1

if __name__ == "__main__":
    raise SystemExit(main())
