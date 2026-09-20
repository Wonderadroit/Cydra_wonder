from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from cydra.canonical_cycle import run_canonical_differential_cycle
from cydra.finding_gate import FindingCandidate, evaluate_finding_graph
from cydra.foundry import require_executed, run_foundry_test, test_path_for
from cydra.hypotheses import Hypothesis as CanonicalHypothesis
from cydra.idempotency_execution import generate_idempotency_test
from cydra.impact import ImpactAssessment, ImpactLevel
from cydra.models import Experiment
from cydra.pipeline import investigate
from cydra.reasoning import plan_idempotency_experiment
from cydra.structural_idempotency import generate_idempotency_hypotheses
from cydra.solidity_model import parse_solidity
from cydra.system_model import Edge, Node, SystemModel

V = Path("benchmarks/011_idempotency_mt_pelerin/IdempotencyTarget.sol")
P = Path("benchmarks/011_idempotency_mt_pelerin/IdempotencyTargetPatched.sol")


def _project(source: Path, root: Path) -> None:
    (root / "src").mkdir(parents=True)
    (root / "test").mkdir()
    (root / "foundry.toml").write_text("[profile.default]\nsrc='src'\ntest='test'\nlibs=[]\n")
    shutil.copy2(source, root / "src" / source.name)


def _side(source: Path, hypothesis, experiment: Experiment, label: str):
    with tempfile.TemporaryDirectory(prefix="cydra-idempotency-") as temp:
        root = Path(temp) / "project"
        _project(source, root)
        model = parse_solidity(root / "src" / source.name)[0]
        test = generate_idempotency_test(
            hypothesis,
            model,
            f"../src/{source.name}",
            model.name,
            test_path_for(root, f"generated/{hypothesis.hypothesis_id}.t.sol"),
            experiment=experiment,
        )
        result = run_foundry_test(root, test, experiment.experiment_id, label)
        require_executed(result)
        return result


def main() -> int:
    result = investigate(
        V,
        target="Mt Pelerin historical double-transaction extracted regression",
        reasoning_surfaces=(generate_idempotency_hypotheses,),
        experiment_planner=plan_idempotency_experiment,
    )
    hypotheses = [
        h for h in result.hypotheses if h.invariant_id.startswith("INV-IDEMPOTENCY-")
    ]
    if not hypotheses:
        raise SystemExit("No idempotency hypothesis extracted")
    hypothesis = hypotheses[0]
    experiment = next(e for e in result.experiments if e.hypothesis_id == hypothesis.hypothesis_id)

    vulnerable = _side(V, hypothesis, experiment, "idempotency-vulnerable")
    patched = _side(P, hypothesis, experiment, "idempotency-patched")

    model = SystemModel()
    contract_id = f"contract:{result.contracts[0].name}"
    function_id = f"function:{result.contracts[0].name}:{hypothesis.target_function}"
    invariant_id = f"invariant:{hypothesis.invariant_id}"
    hypothesis_id = f"hypothesis:{hypothesis.hypothesis_id}"
    observation_id = "idempotency-record-reuse"

    model.add_node(Node(contract_id, "contract", result.contracts[0].name, {}))
    model.add_node(Node(function_id, "function", hypothesis.target_function, {}))
    model.add_node(Node(invariant_id, "invariant", hypothesis.claim, {"status": "inferred"}))
    model.add_node(Node(hypothesis_id, "hypothesis", hypothesis.claim, {"belief": 0.5}))
    model.add_node(
        Node(
            f"observation:{observation_id}",
            "observation",
            "repeated-record-value-release",
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

    cycle = run_canonical_differential_cycle(
        model,
        hypothesis=CanonicalHypothesis(hypothesis.hypothesis_id, hypothesis.claim, 0.5),
        observation_id=observation_id,
        vulnerable=vulnerable,
        patched=patched,
        outcome_id="idempotency-differential",
    )

    impact = ImpactAssessment(
        ImpactLevel.HIGH,
        "value-releasing record transition",
        "The same state record can release its value more than once when repeated in one user-controlled batch.",
        "caller can supply repeated record identifiers and the target holds releasable value",
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
            True,
        ),
        finding_id=f"F-IDEMPOTENCY-{hypothesis.target_function}",
        hypothesis_id=hypothesis_id,
        evidence_ids=cycle.causal_verification.evidence_ids,
        causal_chain_id=cycle.causal_chain.chain_id,
    )
    output = {
        "hypothesis": hypothesis.__dict__,
        "experiment": experiment.__dict__,
        "vulnerable": vulnerable.__dict__,
        "patched": patched.__dict__,
        "causal": cycle.causal_verification.__dict__,
        "finding_gate": gate.decision.value,
        "reasons": list(gate.reasons),
    }
    print(json.dumps(output, indent=2, default=str))
    return 0 if gate.decision.value == "READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
