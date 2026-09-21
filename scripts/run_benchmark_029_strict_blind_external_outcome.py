from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from cydra.canonical_cycle import run_canonical_differential_cycle
from cydra.finding_gate import FindingCandidate, evaluate_finding_graph
from cydra.hypotheses import Hypothesis as CanonicalHypothesis
from cydra.impact import ImpactAssessment, ImpactLevel
from cydra.pipeline import investigate
from cydra.research_loop import run_research_loop
from cydra.system_model import Edge, Node, SystemModel

TARGET_REPO = "https://github.com/code-423n4/2022-06-nested.git"
TARGET_REF = "b4a153c943d54755711a2f7b80cbbf3a5bb49d76"
TARGET_PATH = "contracts/Withdrawer.sol"

VULNERABLE_TEST_SOURCE = r"""// SPDX-License-Identifier: MIT
pragma solidity 0.8.14;

import "forge-std/Test.sol";
import "../Withdrawer.sol";
import "../interfaces/external/IWETH.sol";

contract CydraFalseReturnWETH {
    function transferFrom(address, address, uint256) external pure returns (bool) {
        return false;
    }

    function withdraw(uint256 amount) external {
        require(address(this).balance >= amount, "insufficient mock WETH");
        (bool ok, ) = msg.sender.call{value: amount}("");
        require(ok, "native send failed");
    }

    receive() external payable {}
}

contract CydraExternalOutcomeTest is Test {
    Withdrawer internal withdrawer;
    CydraFalseReturnWETH internal weth;

    function setUp() public {
        weth = new CydraFalseReturnWETH();
        withdrawer = new Withdrawer(IWETH(address(weth)));
        vm.deal(address(weth), 1 ether);
    }

    receive() external payable {}

    function testIgnoredExternalFailureCannotReleaseNativeValue() public {
        uint256 beforeBalance = address(this).balance;
        withdrawer.withdraw(1 ether);
        assertEq(
            address(this).balance,
            beforeBalance,
            "vulnerable path released native value after false transferFrom"
        );
    }
}
"""

PATCHED_TEST_SOURCE = r"""// SPDX-License-Identifier: MIT
pragma solidity 0.8.14;

import "forge-std/Test.sol";
import "../Withdrawer.sol";
import "../interfaces/external/IWETH.sol";

contract CydraFalseReturnWETH {
    function transferFrom(address, address, uint256) external pure returns (bool) {
        return false;
    }

    function withdraw(uint256 amount) external {
        require(address(this).balance >= amount, "insufficient mock WETH");
        (bool ok, ) = msg.sender.call{value: amount}("");
        require(ok, "native send failed");
    }

    receive() external payable {}
}

contract CydraExternalOutcomeTest is Test {
    Withdrawer internal withdrawer;
    CydraFalseReturnWETH internal weth;

    function setUp() public {
        weth = new CydraFalseReturnWETH();
        withdrawer = new Withdrawer(IWETH(address(weth)));
        vm.deal(address(weth), 1 ether);
    }

    function testIgnoredExternalFailureIsStopped() public {
        vm.expectRevert("Cydra: external call failed");
        withdrawer.withdraw(1 ether);
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
        ("npm", "install", "--ignore-scripts", "--no-audit", "--no-fund"),
        cwd=destination, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    subprocess.run(
        ("forge", "install", "foundry-rs/forge-std", "--no-commit"),
        cwd=destination, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    (destination / "foundry.toml").write_text(
        "[profile.default]\n"
        'src = "contracts"\n'
        'test = "contracts/test"\n'
        'libs = ["lib", "node_modules"]\n'
        'solc_version = "0.8.14"\n',
        encoding="utf-8",
    )
    return destination

def write_test(root: Path, label: str) -> None:
    path = root / "contracts" / "test" / "CydraExternalOutcome.t.sol"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(PATCHED_TEST_SOURCE if "patched" in label else VULNERABLE_TEST_SOURCE, encoding="utf-8")

def run_target(root: Path, label: str):
    write_test(root, label)
    completed = subprocess.run(
        ("forge", "test", "--match-test", "testIgnoredExternalFailureCannotReleaseNativeValue|testIgnoredExternalFailureIsStopped", "-vvv"),
        cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    return {
        "experiment_id": f"X-EXTERNAL-OUTCOME-{label}",
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
    old = "        weth.transferFrom(msg.sender, address(this), amount);"
    new = '        require(weth.transferFrom(msg.sender, address(this), amount), "Cydra: external call failed");'
    if old not in source:
        raise RuntimeError("external-outcome control insertion point not found")
    path.write_text(source.replace(old, new, 1), encoding="utf-8")

def canonical_model(hypothesis):
    model = SystemModel()
    function_id = f"function:Withdrawer:{hypothesis.target_function}"
    invariant_id = f"invariant:{hypothesis.invariant_id}"
    hypothesis_id = f"hypothesis:{hypothesis.hypothesis_id}"
    observation_id = "ignored-external-failure"
    model.add_node(Node("contract:Withdrawer", "contract", "Withdrawer",
                        {"provenance": "pinned historical source"}))
    model.add_node(Node(function_id, "function", hypothesis.target_function,
                        {"provenance": "pinned historical source"}))
    model.add_node(Node(invariant_id, "invariant", hypothesis.claim,
                        {"status": "inferred", "confidence": 0.80}))
    model.add_node(Node(hypothesis_id, "hypothesis", hypothesis.claim, {"belief": 0.5}))
    model.add_node(Node(
        f"observation:{observation_id}", "observation",
        "external dependency reports failure before a subsequent native-value transition",
        {"status": "planned", "hypothesis_id": hypothesis_id,
         "target_function_id": function_id, "binding_status": "bound",
         "experiment_binding": {"hypothesis_id": hypothesis_id,
                                "observation_id": f"observation:{observation_id}",
                                "target_function_id": function_id}},
    ))
    model.add_edge(Edge(invariant_id, "informs", hypothesis_id, {}))
    model.add_edge(Edge(f"observation:{observation_id}", "tests", hypothesis_id, {}))
    return model, CanonicalHypothesis(hypothesis.hypothesis_id, hypothesis.claim, 0.5), observation_id

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("backtest-artifacts/strict-blind-external-outcome"))
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="cydra-nested-blind-v-") as tmp:
        target = clone_target(Path(tmp) / "target")
        source = target / TARGET_PATH
        investigation = investigate(source, target=f"{TARGET_REPO}@{TARGET_REF}:{TARGET_PATH}")
        def execute(hypothesis, experiment):
            if not hypothesis.invariant_id.startswith("INV-EXTERNAL-OUTCOME-"):
                raise RuntimeError(
                    "strict blind selector did not choose external-outcome hypothesis: "
                    + hypothesis.hypothesis_id + "/" + hypothesis.target_function
                )
            return run_target(target, "vulnerable")

        loop = run_research_loop(
            investigation.hypotheses,
            investigation.invariants,
            investigation.experiments,
            execute=execute,
            status_of=lambda observation: observation["status"],
            stop_when=lambda _observation: True,
            max_rounds=1,
        )
        if len(loop.rounds) != 1:
            raise RuntimeError("expected exactly one blind research round")
        round_ = loop.rounds[0]
        hypothesis = round_.selection.hypothesis
        experiment = next(e for e in investigation.experiments if e.hypothesis_id == hypothesis.hypothesis_id)
        selection = round_.selection
        vulnerable = round_.observation

    with tempfile.TemporaryDirectory(prefix="cydra-nested-blind-p-") as tmp:
        target = clone_target(Path(tmp) / "target")
        patch_target(target)
        patched = run_target(target, "patched")

    with tempfile.TemporaryDirectory(prefix="cydra-nested-blind-repro-v-") as tmp:
        target = clone_target(Path(tmp) / "target")
        independent_vulnerable = run_target(target, "independent-vulnerable")

    with tempfile.TemporaryDirectory(prefix="cydra-nested-blind-repro-p-") as tmp:
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
        outcome_id="strict-blind-external-outcome-differential",
    )
    reproduction_verified = (
        independent_vulnerable["status"] == "FAIL"
        and independent_patched["status"] == "PASS"
    )
    impact = ImpactAssessment(
        ImpactLevel.HIGH,
        "native value release",
        "The target can release native value after an external token operation reports failure, allowing a caller to receive value without the corresponding token transfer.",
        ("external dependency can return false without reverting", "a later value-release transition remains reachable"),
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
        finding_id=f"F-STRICT-BLIND-EXTERNAL-OUTCOME-{hypothesis.target_function}",
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
        "boundary": "normal class-neutral blind pipeline selected the target hypothesis; the synthetic control changes only validation of the external call result; independent clones reproduce the differential.",
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "result.json").write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))
    return 0 if gate.decision.value == "READY" else 1

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        output = Path("backtest-artifacts/strict-blind-external-outcome")
        output.mkdir(parents=True, exist_ok=True)
        (output / "runner_error.json").write_text(json.dumps({"error_type": type(exc).__name__, "error": str(exc)}, indent=2) + "\n", encoding="utf-8")
        raise
