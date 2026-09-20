from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from cydra.pipeline import investigate
from cydra.structural_read_only_reentrancy import generate_read_only_reentrancy_hypotheses
from cydra.reasoning import plan_read_only_reentrancy_experiment
from cydra.read_only_reentrancy_execution import generate_read_only_reentrancy_test
from cydra.foundry import run_foundry_test, require_executed, test_path_for
from cydra.canonical_cycle import run_canonical_differential_cycle
from cydra.finding_gate import FindingCandidate, evaluate_finding_graph
from cydra.hypotheses import Hypothesis as CH
from cydra.system_model import SystemModel, Node, Edge
from cydra.impact import ImpactAssessment, ImpactLevel

V = Path("benchmarks/012_read_only_reentrancy/ReadOnlyReentrancyTarget.sol")
P = Path("benchmarks/012_read_only_reentrancy/ReadOnlyReentrancyTargetPatched.sol")


def project(src: Path, root: Path) -> None:
    (root / "src").mkdir(parents=True)
    (root / "test").mkdir()
    (root / "foundry.toml").write_text(
        "[profile.default]\nsrc='src'\ntest='test'\nlibs=[]\n",
        encoding="utf-8",
    )
    shutil.copy2(src, root / "src" / src.name)


def side(src: Path, hypothesis, experiment, label: str, patched: bool):
    with tempfile.TemporaryDirectory(prefix="cydra-readonly-") as tmp:
        root = Path(tmp) / "p"
        project(src, root)
        from cydra.solidity_model import parse_solidity

        contracts = parse_solidity(root / "src" / src.name)
        target_contract = next(
            contract
            for contract in contracts
            if any(f.name == hypothesis.target_function for f in contract.functions)
        )
        observer = next(
            contract for contract in contracts if contract.name.startswith("ReentrantObserver")
        )
        test_path = test_path_for(root, f"generated/{hypothesis.hypothesis_id}.t.sol")
        generated = generate_read_only_reentrancy_test(
            hypothesis,
            target_contract,
            f"../src/{src.name}",
            target_contract.name,
            observer.name,
            test_path,
            experiment=experiment,
            patched=patched,
        )
        result = run_foundry_test(root, generated, experiment.experiment_id, label)
        require_executed(result)
        return result


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    result = investigate(
        root / V,
        target="historical read-only reentrancy extracted regression",
        reasoning_surfaces=(generate_read_only_reentrancy_hypotheses,),
        experiment_planner=plan_read_only_reentrancy_experiment,
    )
    hypotheses = [
        h for h in result.hypotheses
        if h.invariant_id.startswith("INV-READONLY-REENTRANCY-")
    ]
    if not hypotheses:
        raise SystemExit("No read-only reentrancy hypothesis extracted")
    hypothesis = hypotheses[0]
    experiment = next(
        e for e in result.experiments if e.hypothesis_id == hypothesis.hypothesis_id
    )

    vulnerable = side(V, hypothesis, experiment, "readonly-vulnerable", False)
    patched = side(P, hypothesis, experiment, "readonly-patched", True)

    contract = next(
        c for c in result.contracts
        if any(f.name == hypothesis.target_function for f in c.functions)
    )
    model = SystemModel()
    cid = f"contract:{contract.name}"
    fid = f"function:{contract.name}:{hypothesis.target_function}"
    iid = f"invariant:{hypothesis.invariant_id}"
    hid = f"hypothesis:{hypothesis.hypothesis_id}"
    oid = "readonly-reentrancy"
    model.add_node(Node(cid, "contract", contract.name, {}))
    model.add_node(Node(fid, "function", hypothesis.target_function, {}))
    model.add_node(Node(iid, "invariant", hypothesis.claim, {"status": "inferred"}))
    model.add_node(Node(hid, "hypothesis", hypothesis.claim, {"belief": 0.5}))
    model.add_node(
        Node(
            f"observation:{oid}",
            "observation",
            "view observes transient state during external callback",
            {
                "status": "planned",
                "hypothesis_id": hid,
                "target_function_id": fid,
                "binding_status": "bound",
                "experiment_binding": {
                    "hypothesis_id": hid,
                    "observation_id": f"observation:{oid}",
                    "target_function_id": fid,
                },
            },
        )
    )
    model.add_edge(Edge(iid, "informs", hid, {}))
    model.add_edge(Edge(f"observation:{oid}", "tests", hid, {}))

    cycle = run_canonical_differential_cycle(
        model,
        hypothesis=CH(hypothesis.hypothesis_id, hypothesis.claim, 0.5),
        observation_id=oid,
        vulnerable=vulnerable,
        patched=patched,
        outcome_id="readonly-reentrancy-differential",
    )
    impact = ImpactAssessment(
        ImpactLevel.HIGH,
        "economic decisions based on an externally observed transient value",
        "A consumer can read a state-derived value while the producing transition is only partially settled.",
        "caller can receive the external callback and invoke the public view before settlement",
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
        finding_id=f"F-READONLY-{hypothesis.target_function}",
        hypothesis_id=hid,
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
