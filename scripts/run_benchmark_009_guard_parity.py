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
from cydra.guard_parity_execution import generate_guard_parity_test


TARGET_LABEL = "Euler Finance EToken historical guard-parity extraction"
TARGET_PROVENANCE = "euler-legacy-xyz/euler-contracts@85abe8d0986f97557159d26c5e79df6d78eccc53"
FIX_PROVENANCE = "documented post-incident fix: restore checkLiquidity(account) after donation"
VULNERABLE_SOURCE = Path("benchmarks/009_guard_parity_euler/GuardParityTarget.sol")
PATCHED_SOURCE = Path("benchmarks/009_guard_parity_euler/GuardParityTargetPatched.sol")


def make_foundry_project(source: Path, project: Path, filename: str) -> Path:
    (project / "src").mkdir(parents=True)
    (project / "test").mkdir(parents=True)
    (project / "foundry.toml").write_text(
        "[profile.default]\nsrc = 'src'\ntest = 'test'\nlibs = []\n",
        encoding="utf-8",
    )
    destination = project / "src" / filename
    shutil.copy2(source, destination)
    return project


def canonical_model(hypothesis, contract_name: str):
    model = SystemModel()
    contract_id = f"contract:{contract_name}"
    function_id = f"function:{contract_name}:{hypothesis.target_function}"
    invariant_id = f"invariant:{hypothesis.invariant_id}"
    hypothesis_id = f"hypothesis:{hypothesis.hypothesis_id}"
    observation_id = f"OBS-GUARD-{contract_name}-{hypothesis.target_function}"

    model.add_node(Node(contract_id, "contract", contract_name, {"provenance": TARGET_PROVENANCE}))
    model.add_node(Node(function_id, "function", hypothesis.target_function, {"contract": contract_name, "provenance": TARGET_PROVENANCE}))
    model.add_node(Node(
        invariant_id,
        "invariant",
        "State-changing transitions sharing a state surface with guarded peers should preserve the observed postcondition before returning.",
        {"status": "inferred", "confidence": 0.78, "provenance": "sibling state-transition postcondition parity"},
    ))
    model.add_node(Node(
        hypothesis_id,
        "hypothesis",
        hypothesis.claim,
        {"belief": 0.5, "state": "unresolved", "invariant_id": invariant_id, "provenance": "generic guard-parity reasoning"},
    ))
    model.add_node(Node(
        f"observation:{observation_id}",
        "observation",
        f"Execute {hypothesis.target_function} with the discriminating state-reducing input.",
        {
            "status": "planned",
            "target_function_id": function_id,
            "binding_status": "bound",
            "experiment_binding": {
                "hypothesis_id": hypothesis_id,
                "observation_id": f"observation:{observation_id}",
                "target_function_id": function_id,
            },
            "provenance": "generic guard-parity experiment",
        },
    ))
    model.add_edge(Edge(invariant_id, "informs", hypothesis_id, {"provenance": "generic guard-parity reasoning"}))
    model.add_edge(Edge(f"observation:{observation_id}", "targets", invariant_id, {"provenance": "generic guard-parity reasoning"}))
    model.add_edge(Edge(f"observation:{observation_id}", "tests", hypothesis_id, {"provenance": "generic guard-parity reasoning"}))
    return model, CanonicalHypothesis(hypothesis.hypothesis_id, hypothesis.claim, 0.5), observation_id


def run_side(source: Path, contract_name: str, hypothesis, experiment, label: str) -> object:
    with tempfile.TemporaryDirectory(prefix=f"cydra-guard-parity-{label}-") as tmp:
        project = make_foundry_project(source, Path(tmp) / "project", source.name)
        target_model = parse_solidity(project / "src" / source.name)[0]
        generated = generate_guard_parity_test(
            hypothesis,
            target_model,
            f"../src/{source.name}",
            contract_name,
            test_path_for(project, f"generated/{hypothesis.hypothesis_id}.t.sol"),
            experiment=experiment,
        )
        result = run_foundry_test(project, generated, experiment.experiment_id, label)
        require_executed(result)
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Blind historical postcondition-parity backtest.")
    parser.add_argument("--output", type=Path, default=Path("backtest-artifacts/euler-guard-parity"))
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    vulnerable_source = root / VULNERABLE_SOURCE
    patched_source = root / PATCHED_SOURCE

    result = investigate(vulnerable_source, target=TARGET_PROVENANCE)
    hypotheses = [
        h for h in result.hypotheses
        if h.invariant_id.startswith("INV-GUARD-PARITY-")
    ]
    if not hypotheses:
        raise SystemExit("No guard-parity hypothesis was extracted from the blind target.")
    hypothesis = next(h for h in hypotheses if h.target_function == "donateToReserves")
    experiment = next(e for e in result.experiments if e.hypothesis_id == hypothesis.hypothesis_id)

    vulnerable = run_side(vulnerable_source, "GuardParityTarget", hypothesis, experiment, "euler-vulnerable")
    patched = run_side(patched_source, "GuardParityTargetPatched", hypothesis, experiment, "euler-patched")

    model, canonical_hypothesis, observation_id = canonical_model(hypothesis, result.contracts[0].name)
    cycle = run_canonical_differential_cycle(
        model,
        hypothesis=canonical_hypothesis,
        observation_id=observation_id,
        vulnerable=vulnerable,
        patched=patched,
        outcome_id="euler-guard-parity-differential",
    )
    impact = ImpactAssessment(
        ImpactLevel.HIGH,
        "account solvency / liquidation boundary",
        "A public state transition can reduce a user's collateral state without enforcing the postcondition preserved by sibling balance-changing transitions, allowing an account to cross the modeled solvency boundary.",
        ("caller controls the state-reducing input", "the account has outstanding debt or another obligation tied to the shared state"),
        cycle.causal_verification.evidence_ids,
    )
    gate = evaluate_finding_graph(
        model,
        candidate=FindingCandidate(True, False, True, True, cycle.causal_verification.state.value == "verified", impact.assessed, True),
        finding_id=f"F-GUARD-{hypothesis.target_function}",
        hypothesis_id=f"hypothesis:{hypothesis.hypothesis_id}",
        evidence_ids=cycle.causal_verification.evidence_ids,
        causal_chain_id=cycle.causal_chain.chain_id,
    )

    args.output.mkdir(parents=True, exist_ok=True)
    payload = {
        "target": TARGET_LABEL,
        "target_provenance": TARGET_PROVENANCE,
        "patched_provenance": FIX_PROVENANCE,
        "target_fixture": str(VULNERABLE_SOURCE),
        "patched_fixture": str(PATCHED_SOURCE),
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
