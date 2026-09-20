from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from cydra.canonical_cycle import run_canonical_differential_cycle
from cydra.finding_gate import FindingCandidate, evaluate_finding_graph
from cydra.foundry import require_executed, run_foundry_test, test_path_for
from cydra.hypotheses import Hypothesis as CanonicalHypothesis
from cydra.impact import ImpactAssessment, ImpactLevel
from cydra.pipeline import investigate
from cydra.signature_replay_execution import generate_signature_replay_test
from cydra.signature_replay_planning import plan_signature_replay_experiment
from cydra.solidity_model import parse_solidity
from cydra.structural_signature_replay import generate_signature_replay_hypotheses
from cydra.system_model import Edge, Node, SystemModel

TARGET_REPO = "https://github.com/sherlock-audit/2024-10-ethos-network.git"
TARGET_REF = "main-source-snapshot"
TARGET_PATH = "ethos/packages/contracts/contracts/EthosAttestation.sol"
VULNERABLE = Path("benchmarks/018_signature_replay/SignatureReplayTarget.sol")
PATCHED = Path("benchmarks/018_signature_replay/SignatureReplayTargetPatched.sol")

def load_target(root: Path) -> Path:
    return root / "benchmarks/018_signature_replay/EthosAttestationTargetSnapshot.sol"

def run_fixture(source: Path, hypothesis, experiment, label: str):
    with tempfile.TemporaryDirectory(prefix="cydra-signature-domain-") as tmp:
        root = Path(tmp) / "project"
        (root / "src").mkdir(parents=True)
        (root / "test").mkdir(parents=True)
        (root / "foundry.toml").write_text("[profile.default]\nsrc='src'\ntest='test'\nlibs=[]\n", encoding="utf-8")
        destination = root / "src" / source.name
        destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        model = parse_solidity(destination)[0]
        generated = generate_signature_replay_test(
            hypothesis,
            model,
            f"../src/{source.name}",
            model.name,
            test_path_for(root, f"generated/{hypothesis.hypothesis_id}.t.sol"),
            experiment=experiment,
        )
        result = run_foundry_test(root, generated, experiment.experiment_id, label)
        require_executed(result)
        return result

def canonical_model(hypothesis):
    model = SystemModel()
    contract_id = "contract:SignatureAuthorization"
    function_id = f"function:SignatureAuthorization:{hypothesis.target_function}"
    invariant_id = f"invariant:{hypothesis.invariant_id}"
    hypothesis_id = f"hypothesis:{hypothesis.hypothesis_id}"
    observation_id = "signature-domain"
    model.add_node(Node(contract_id, "contract", "SignatureAuthorization", {"provenance": "source-derived causal fixture"}))
    model.add_node(Node(function_id, "function", hypothesis.target_function, {"provenance": "historical-source-extraction"}))
    model.add_node(Node(invariant_id, "invariant", hypothesis.claim, {"status": "inferred", "confidence": 0.82}))
    model.add_node(Node(hypothesis_id, "hypothesis", hypothesis.claim, {"belief": 0.5}))
    model.add_node(Node(
        f"observation:{observation_id}",
        "observation",
        "reuse one signed authorization on a second deployment",
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
    parser.add_argument("--output", type=Path, default=Path("backtest-artifacts/signature-replay"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]

    target = load_target(root)
    result = investigate(
        target,
        target=f"{TARGET_REPO}@main:{TARGET_PATH}",
        reasoning_surfaces=(generate_signature_replay_hypotheses,),
        experiment_planner=plan_signature_replay_experiment,
    )
    hypotheses = [h for h in result.hypotheses if h.invariant_id.startswith("INV-SIGNATURE-REPLAY-")]
    if len(hypotheses) != 1:
        raise SystemExit(f"expected one blind signature-replay hypothesis, got {len(hypotheses)}")
    hypothesis = hypotheses[0]
    experiment = next(e for e in result.experiments if e.hypothesis_id == hypothesis.hypothesis_id)

    vulnerable = run_fixture(root / VULNERABLE, hypothesis, experiment, "signature-vulnerable")
    patched = run_fixture(root / PATCHED, hypothesis, experiment, "signature-patched")
    model, canonical_hypothesis, observation_id = canonical_model(hypothesis)
    cycle = run_canonical_differential_cycle(
        model,
        hypothesis=canonical_hypothesis,
        observation_id=observation_id,
        vulnerable=vulnerable,
        patched=patched,
        outcome_id="signature-replay-differential",
    )

    independent_vulnerable = run_fixture(root / VULNERABLE, hypothesis, experiment, "signature-reproduction-vulnerable")
    independent_patched = run_fixture(root / PATCHED, hypothesis, experiment, "signature-reproduction-patched")
    reproduction_verified = independent_vulnerable.status == "FAIL" and independent_patched.status == "PASS"

    impact = ImpactAssessment(
        ImpactLevel.HIGH,
        "cross-deployment authorization integrity",
        "A valid signed authorization can be accepted by another deployment when the signed message is not bound to the execution domain.",
        "the same signer and business inputs exist on another deployment",
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
        finding_id=f"F-SIGNATURE-REPLAY-{hypothesis.target_function}",
        hypothesis_id=f"hypothesis:{hypothesis.hypothesis_id}",
        evidence_ids=cycle.causal_verification.evidence_ids,
        causal_chain_id=cycle.causal_chain.chain_id,
    )

    payload = {
        "historical_target": {"repo": TARGET_REPO, "ref": TARGET_REF, "path": TARGET_PATH},
        "hypothesis": hypothesis.__dict__,
        "experiment": experiment.__dict__,
        "vulnerable": vulnerable.__dict__,
        "patched": patched.__dict__,
        "causal_verification": cycle.causal_verification.__dict__,
        "independent_vulnerable": independent_vulnerable.__dict__,
        "independent_patched": independent_patched.__dict__,
        "reproduction_verified": reproduction_verified,
        "finding_gate": gate.decision.value,
        "ground_truth_note": "Historical report was not used for hypothesis generation; post-run corroboration only.",
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "result.json").write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))
    return 0 if gate.decision.value == "READY" else 1

if __name__ == "__main__":
    raise SystemExit(main())
