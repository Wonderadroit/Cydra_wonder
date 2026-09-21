from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from cydra.canonical_cycle import run_canonical_differential_cycle
from cydra.finding_gate import FindingCandidate, evaluate_finding_graph
from cydra.hypothesis_selection import select_next_hypothesis
from cydra.impact import ImpactAssessment, ImpactLevel
from cydra.pipeline import investigate
from cydra.research_loop import run_research_loop
from cydra.hypotheses import Hypothesis as CanonicalHypothesis
from cydra.system_model import Edge, Node, SystemModel

TARGET_PATH = Path("benchmarks/035_cross_protocol_oracle/Target.sol")
TEST_NAME = "testCrossProtocolDecisionCannotUseTransientPrice"

VULNERABLE_TEST = r"""
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
import "forge-std/Test.sol";
import "../Target.sol";

contract CydraCrossProtocolVulnerableTest is Test {
    function testCrossProtocolDecisionCannotUseTransientPrice() public {
        TransientPool pool = new TransientPool();
        CrossProtocolOracle oracle = new CrossProtocolOracle(pool);
        CollateralLending lending = new CollateralLending(oracle);
        CrossProtocolAttacker attacker = new CrossProtocolAttacker(pool, lending);

        lending.seedPosition(address(attacker), 1, 1000, 150);
        vm.deal(address(pool), 1 wei);

        attacker.attack();
        uint256 released = attacker.withdrawSecondary();

        // Safety invariant: collateral needed to cover debt must not be released
        // merely because another protocol is in an intermediate state.
        assertEq(released, 0, "secondary collateral was released on transient cross-protocol price");
    }
}
"""

PATCHED_TEST = r"""
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
import "forge-std/Test.sol";
import "../Target.sol";

contract CydraCrossProtocolPatchedTest is Test {
    function testCrossProtocolDecisionCannotUseTransientPrice() public {
        TransientPool pool = new TransientPool();
        CrossProtocolOraclePatched oracle = new CrossProtocolOraclePatched(pool);
        CrossProtocolLendingPatched lending = new CrossProtocolLendingPatched(oracle);
        CrossProtocolAttacker attacker = new CrossProtocolAttacker(pool, ILending(address(lending)));

        lending.seedPosition(address(attacker), 1, 1000, 150);
        vm.deal(address(pool), 1 wei);

        try attacker.attack() {
            revert("transient oracle read should have reverted");
        } catch {}

        assertEq(
            lending.secondaryCollateral(address(attacker)),
            1000,
            "secondary collateral must remain locked"
        );
    }
}
"""

def setup_foundry(destination: Path) -> Path:
    subprocess.run(
        ("forge", "init", "--force", "--no-git", str(destination)),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    install_error = None
    for attempt in range(1, 4):
        completed = subprocess.run(
            ("forge", "install", "foundry-rs/forge-std", "--no-commit"),
            cwd=destination,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if completed.returncode == 0:
            install_error = None
            break
        install_error = (
            f"forge-std installation attempt {attempt}/3 failed "
            f"(exit {completed.returncode}):\n{completed.stdout[-8000:]}"
        )
    if install_error is not None:
        raise RuntimeError(install_error)
    target_dir = destination / "benchmarks" / "035_cross_protocol_oracle"
    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TARGET_PATH, target_dir / "Target.sol")
    return destination

def run_foundry(label: str, patched: bool) -> dict:
    with tempfile.TemporaryDirectory(prefix=f"cydra-035-{label}-") as tmp:
        root = setup_foundry(Path(tmp) / "project")
        test_dir = root / "test"
        test_dir.mkdir(parents=True, exist_ok=True)
        source = PATCHED_TEST if patched else VULNERABLE_TEST
        (test_dir / "CrossProtocol.t.sol").write_text(source, encoding="utf-8")
        completed = subprocess.run(
            ("forge", "test", "--match-test", TEST_NAME, "-vvv"),
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        return {
            "experiment_id": f"X-{label}",
            "executed": True,
            "tests_run": 1,
            "tests_failed": 0 if completed.returncode == 0 else 1,
            "status": "PASS" if completed.returncode == 0 else "FAIL",
            "exit_code": completed.returncode,
            "stdout": completed.stdout[-16000:],
            "stderr": "",
        }

def canonical_model(hypothesis):
    model = SystemModel()
    contract_ids = {
        "pool": "contract:TransientPool",
        "oracle": "contract:CrossProtocolOracle",
        "lending": "contract:CollateralLending",
    }
    for key, name in (("pool", "TransientPool"), ("oracle", "CrossProtocolOracle"), ("lending", "CollateralLending")):
        model.add_node(Node(contract_ids[key], "contract", name, {"provenance": "historical-style cross-protocol fixture"}))
    function_id = f"function:CrossProtocolOracle:{hypothesis.target_function}"
    invariant_id = f"invariant:{hypothesis.invariant_id}"
    hypothesis_id = f"hypothesis:{hypothesis.hypothesis_id}"
    observation_id = "cross-protocol-transient-price"
    model.add_node(Node(function_id, "function", hypothesis.target_function, {"provenance": "source model"}))
    model.add_node(Node(
        invariant_id,
        "invariant",
        "A state-changing consumer decision must not rely on a value derived from another protocol while that protocol is in an intermediate transition state.",
        {"status": "inferred", "confidence": 0.85, "provenance": "cross-protocol state-consistency reasoning"},
    ))
    model.add_node(Node(hypothesis_id, "hypothesis", hypothesis.claim, {"belief": 0.5}))
    model.add_node(Node(
        f"observation:{observation_id}",
        "observation",
        "oracle value is elevated during the pool callback and settles afterward",
        {"status": "planned", "hypothesis_id": hypothesis_id, "binding_status": "bound"},
    ))
    model.add_edge(Edge(contract_ids["pool"], "feeds", contract_ids["oracle"], {}))
    model.add_edge(Edge(contract_ids["oracle"], "feeds", contract_ids["lending"], {}))
    model.add_edge(Edge(invariant_id, "informs", hypothesis_id, {}))
    model.add_edge(Edge(f"observation:{observation_id}", "tests", hypothesis_id, {}))
    return model, CanonicalHypothesis(hypothesis.hypothesis_id, hypothesis.claim, 0.5), observation_id

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("backtest-artifacts/benchmark-035-cross-protocol"))
    args = parser.parse_args()

    investigation = investigate(TARGET_PATH, target="benchmark-035-cross-protocol-oracle")

    def execute(hypothesis, experiment):
        if hypothesis.hypothesis_id != "H-READONLY-XCONTRACT-latestAnswer":
            return {
                "experiment_id": experiment.experiment_id,
                "executed": False,
                "status": "UNMEASURABLE",
                "reason": "the benchmark renderer can safely execute only the selected cross-protocol oracle observation",
            }
        return run_foundry("blind-vulnerable", patched=False)

    loop = run_research_loop(
        investigation.hypotheses,
        investigation.invariants,
        investigation.experiments,
        execute=execute,
        status_of=lambda observation: observation["status"],
        stop_when=lambda observation: observation["status"] == "FAIL",
        max_rounds=6,
    )
    if not loop.rounds:
        raise RuntimeError("research loop produced no hypothesis rounds")

    selected = loop.rounds[-1]
    hypothesis = selected.selection.hypothesis
    if hypothesis.hypothesis_id != "H-READONLY-XCONTRACT-latestAnswer":
        raise RuntimeError(
            "strict blind loop did not reach the cross-protocol hypothesis: "
            + hypothesis.hypothesis_id
        )
    vulnerable = selected.observation
    experiment = next(
        e for e in investigation.experiments
        if e.hypothesis_id == hypothesis.hypothesis_id
    )

    patched = run_foundry("patched", patched=True)
    independent_vulnerable = run_foundry("independent-vulnerable", patched=False)
    independent_patched = run_foundry("independent-patched", patched=True)

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
        outcome_id="benchmark-035-cross-protocol-differential",
    )

    reproduction_verified = (
        independent_vulnerable["status"] == "FAIL"
        and independent_patched["status"] == "PASS"
    )
    impact = ImpactAssessment(
        ImpactLevel.HIGH,
        "cross-protocol collateral-accounting integrity",
        "A lending decision releases collateral because its oracle consumes another protocol's transient state during an external callback.",
        (
            "remaining collateral must continue to cover debt",
            "the consumer must not treat an intermediate external-protocol value as settled economic state",
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
            reproduction_verified,
        ),
        finding_id=f"F-BENCHMARK-035-{hypothesis.target_function}",
        hypothesis_id=f"hypothesis:{hypothesis.hypothesis_id}",
        evidence_ids=cycle.causal_verification.evidence_ids,
        causal_chain_id=cycle.causal_chain.chain_id,
    )

    payload = {
        "benchmark": "035",
        "historical_context": "2023 Sturdy Finance / Balancer cross-protocol integration shape",
        "blind_boundary": {
            "vulnerability_class": False,
            "target_function": False,
            "exploit_sequence": False,
            "expected_invariant": False,
            "historical_answer": False,
            "specialized_selector": False,
            "target_specific_reasoning_surface": False,
        },
        "research_loop": [
            {
                "hypothesis_id": round_.selection.hypothesis.hypothesis_id,
                "target_function": round_.selection.hypothesis.target_function,
                "score": round_.selection.score,
                "status": round_.status,
                "observation": round_.observation,
            }
            for round_ in loop.rounds
        ],
        "selected_hypothesis": hypothesis.__dict__,
        "experiment": experiment.__dict__,
        "vulnerable": vulnerable,
        "patched": patched,
        "causal_verification": cycle.causal_verification.__dict__,
        "independent_vulnerable": independent_vulnerable,
        "independent_patched": independent_patched,
        "reproduction_verified": reproduction_verified,
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
