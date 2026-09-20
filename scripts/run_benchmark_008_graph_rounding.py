from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from cydra.canonical_cycle import run_canonical_differential_cycle
from cydra.foundry import require_executed, run_foundry_test, test_path_for
from cydra.finding_gate import FindingCandidate, evaluate_finding_graph
from cydra.hypotheses import Hypothesis as CanonicalHypothesis
from cydra.impact import ImpactAssessment, ImpactLevel
from cydra.pipeline import investigate
from cydra.solidity_model import parse_solidity
from cydra.system_model import Edge, Node, SystemModel
from cydra.weighted_average_rounding_execution import generate_weighted_average_rounding_test


TARGET_REPO = "https://github.com/graphprotocol/contracts"
TARGET_REF = "25d07528b1107682674bfe0bed56523238fcacb1^"
PATCHED_REF = "25d07528b1107682674bfe0bed56523238fcacb1"
TARGET_PATH = "packages/contracts/contracts/staking/libs/MathUtils.sol"


def clone(repo: str, ref: str, destination: Path) -> None:
    subprocess.run(("git", "clone", "--no-tags", "--filter=blob:none", repo, str(destination)), check=True)
    subprocess.run(("git", "-C", str(destination), "checkout", "--detach", ref), check=True)


def make_foundry_project(source: Path, project: Path) -> Path:
    (project / "src").mkdir(parents=True)
    (project / "test").mkdir(parents=True)
    (project / "foundry.toml").write_text(
        "[profile.default]\nsrc = 'src'\ntest = 'test'\nlibs = []\n",
        encoding="utf-8",
    )
    math_source = source.read_text(encoding="utf-8")
    math_source = math_source.replace(
        'import "@openzeppelin/contracts/math/SafeMath.sol";',
        'import "./SafeMath.sol";',
    )
    (project / "src" / "MathUtils.sol").write_text(math_source, encoding="utf-8")
    (project / "src" / "SafeMath.sol").write_text(
        """// SPDX-License-Identifier: MIT
pragma solidity ^0.7.6;
library SafeMath {
    function add(uint256 a, uint256 b) internal pure returns (uint256) { return a + b; }
    function sub(uint256 a, uint256 b) internal pure returns (uint256) { require(b <= a); return a - b; }
    function mul(uint256 a, uint256 b) internal pure returns (uint256) { return a * b; }
    function div(uint256 a, uint256 b) internal pure returns (uint256) { require(b != 0); return a / b; }
}
""",
        encoding="utf-8",
    )
    return project


def canonical_model(hypothesis, contract_name: str):
    model = SystemModel()
    contract_id = f"contract:{contract_name}"
    function_id = f"function:{contract_name}:{hypothesis.target_function}"
    invariant_id = "invariant:INV-ROUND-001"
    hypothesis_id = f"hypothesis:{hypothesis.hypothesis_id}"
    observation_id = f"OBS-ROUND-{contract_name}-{hypothesis.target_function}"

    model.add_node(Node(contract_id, "contract", contract_name, {"provenance": "solidity_model"}))
    model.add_node(Node(function_id, "function", hypothesis.target_function, {"contract": contract_name, "provenance": "solidity_model"}))
    model.add_node(Node(
        invariant_id,
        "invariant",
        "A weighted average used for a conservative boundary must not round below the mathematical average when fractional.",
        {"status": "inferred", "confidence": 0.80, "provenance": "structural weighted-average arithmetic"},
    ))
    model.add_node(Node(
        hypothesis_id,
        "hypothesis",
        hypothesis.claim,
        {"belief": 0.5, "state": "unresolved", "invariant_id": invariant_id, "provenance": "structural rounding reasoning"},
    ))
    model.add_node(Node(
        f"observation:{observation_id}",
        "observation",
        f"Execute {hypothesis.target_function} with a fractional weighted-average boundary.",
        {
            "status": "planned",
            "target_function_id": function_id,
            "binding_status": "bound",
            "experiment_binding": {
                "hypothesis_id": hypothesis_id,
                "observation_id": f"observation:{observation_id}",
                "target_function_id": function_id,
            },
            "provenance": "structural rounding experiment",
        },

    ))
    model.add_edge(Edge(invariant_id, "informs", hypothesis_id, {"provenance": "structural rounding reasoning"}))
    model.add_edge(Edge(f"observation:{observation_id}", "targets", invariant_id, {"provenance": "structural rounding reasoning"}))
    model.add_edge(Edge(f"observation:{observation_id}", "tests", hypothesis_id, {"provenance": "structural rounding reasoning"}))
    return model, CanonicalHypothesis(hypothesis.hypothesis_id, hypothesis.claim, 0.5), observation_id


def patched_callable_name(model) -> str:
    candidates = [
        function.name
        for function in model.functions
        if len(function.parameters) == 4
        and all(parameter.type.startswith("uint") for parameter in function.parameters)
        and function.name != "weightedAverage"
    ]
    if not candidates:
        raise RuntimeError("patched target has no structural weighted-average callable")
    return candidates[0]


def run_side(checkout: Path, source: Path, hypothesis, experiment, label: str, callable_name: str | None = None) -> tuple[object, Path]:
    with tempfile.TemporaryDirectory(prefix=f"cydra-rounding-{label}-") as tmp:
        project = make_foundry_project(source, Path(tmp) / "project")
        target_model = parse_solidity(project / "src" / "MathUtils.sol")[0]
        generated = generate_weighted_average_rounding_test(
            hypothesis,
            target_model,
            "../src/MathUtils.sol",
            "MathUtils",
            test_path_for(project, f"generated/{hypothesis.hypothesis_id}.t.sol"),
            experiment=experiment,
            callable_name=callable_name,
        )
        # Keep the temporary project alive while Foundry executes.
        result = run_foundry_test(project, generated, experiment.experiment_id, label)
        require_executed(result)
        saved = Path(tmp).parent / f"cydra-{label}-{hypothesis.hypothesis_id}.t.sol"
        shutil.copy2(generated, saved)
        return result, saved


def main() -> int:
    parser = argparse.ArgumentParser(description="Blind historical weighted-average rounding backtest.")
    parser.add_argument("--output", type=Path, default=Path("backtest-artifacts/graph-rounding"))
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="cydra-graph-rounding-target-") as tmp:
        base = Path(tmp)
        vulnerable_checkout = base / "vulnerable"
        patched_checkout = base / "patched"
        clone(TARGET_REPO, TARGET_REF, vulnerable_checkout)
        clone(TARGET_REPO, PATCHED_REF, patched_checkout)

        vulnerable_source = vulnerable_checkout / TARGET_PATH
        result = investigate(
            vulnerable_source,
            target=f"{TARGET_REPO}@{TARGET_REF}",
        )
        hypotheses = [h for h in result.hypotheses if h.invariant_id == "INV-ROUND-001"]
        if not hypotheses:
            raise SystemExit("No weighted-average rounding hypothesis was extracted from the blind target.")
        hypothesis = hypotheses[0]
        experiment = next(e for e in result.experiments if e.hypothesis_id == hypothesis.hypothesis_id)

        vulnerable, _ = run_side(vulnerable_checkout, vulnerable_source, hypothesis, experiment, "graph-vulnerable")
        patched_source = patched_checkout / TARGET_PATH
        patched_model = parse_solidity(patched_source)[0]
        patched_name = patched_callable_name(patched_model)
        patched, _ = run_side(
            patched_checkout,
            patched_source,
            hypothesis,
            experiment,
            "graph-patched",
            callable_name=patched_name,
        )

        model, canonical_hypothesis, observation_id = canonical_model(hypothesis, result.contracts[0].name)
        cycle = run_canonical_differential_cycle(
            model,
            hypothesis=canonical_hypothesis,
            observation_id=observation_id,
            vulnerable=vulnerable,
            patched=patched,
            outcome_id="graph-rounding-differential",
        )
        impact = ImpactAssessment(
            ImpactLevel.HIGH,
            "thawing-period enforcement",
            "A fractional weighted-average boundary rounds down, allowing the newly combined lock period to be shorter than the conservative mathematical average.",
            ("caller controls the new unstake amount", "the weighted average is used to calculate a lock duration"),
            cycle.causal_verification.evidence_ids,
        )
        gate = evaluate_finding_graph(
            model,
            candidate=FindingCandidate(True, False, True, True, cycle.causal_verification.state.value == "verified", impact.assessed, True),
            finding_id=f"F-ROUND-{hypothesis.target_function}",
            hypothesis_id=f"hypothesis:{hypothesis.hypothesis_id}",
            evidence_ids=cycle.causal_verification.evidence_ids,
            causal_chain_id=cycle.causal_chain.chain_id,
        )

        args.output.mkdir(parents=True, exist_ok=True)
        payload = {
            "target": f"{TARGET_REPO}@{TARGET_REF}",
            "patched_target": f"{TARGET_REPO}@{PATCHED_REF}",
            "target_path": TARGET_PATH,
            "hypothesis": hypothesis.__dict__,
            "experiment": experiment.__dict__,
            "execution": {"vulnerable": vulnerable.__dict__, "patched": patched.__dict__},
            "canonical_cycle": {
                "verification": cycle.verification.__dict__,
                "causal_chain": cycle.causal_chain.__dict__,
                "causal_verification": cycle.causal_verification.__dict__,
            },
            "impact": impact.__dict__,
            "finding_gate": {"decision": gate.decision.value, "reasons": list(gate.reasons)},
        }
        (args.output / "result.json").write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
        print(json.dumps(payload, indent=2, default=str))

        return 0 if gate.decision.value == "READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
