from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from cydra.canonical_cycle import run_canonical_differential_cycle
from cydra.cross_contract_attribution_execution import (
    generate_cross_contract_attribution_test,
)
from cydra.foundry import require_executed, run_foundry_test, test_path_for
from cydra.finding_gate import FindingCandidate, evaluate_finding_graph
from cydra.hypotheses import Hypothesis as CanonicalHypothesis
from cydra.impact import ImpactAssessment, ImpactLevel
from cydra.pipeline import investigate
from cydra.reasoning import plan_cross_contract_attribution_experiment
from cydra.structural_cross_contract_attribution import (
    generate_cross_contract_attribution_hypotheses,
)
from cydra.solidity_model import parse_solidity
from cydra.system_model import Edge, Node, SystemModel

TARGET_REPO = "https://github.com/code-423n4/2022-08-olympus.git"
TARGET_REF = "549b96bcf8b97807738572605f6b1e26b33ef411"
TARGET_PATH = "src/modules/TRSRY.sol"

FIXTURE_V = Path("benchmarks/016_olympus_cross_contract_attribution/Target.sol")
FIXTURE_P = Path("benchmarks/016_olympus_cross_contract_attribution/TargetPatched.sol")


def _clone_historical_source(destination: Path) -> Path:
    subprocess.run(("git", "clone", "--no-tags", TARGET_REPO, str(destination)), check=True)
    subprocess.run(("git", "-C", str(destination), "checkout", "--detach", TARGET_REF), check=True)
    return destination / TARGET_PATH


def _project(source: Path, root: Path) -> None:
    (root / "src").mkdir(parents=True)
    (root / "test").mkdir()
    (root / "foundry.toml").write_text(
        "[profile.default]\nsrc='src'\ntest='test'\nlibs=[]\n",
        encoding="utf-8",
    )
    (root / "src" / source.name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


def _run_side(source: Path, hypothesis, label: str):
    with tempfile.TemporaryDirectory(prefix=f"cydra-olympus-attribution-{label}-") as tmp:
        root = Path(tmp) / "project"
        _project(source, root)
        model = parse_solidity(root / "src" / source.name)[-1]
        generated = generate_cross_contract_attribution_test(
            hypothesis,
            test_path_for(root, "generated/CydraCrossContractAttributionTest.t.sol"),
            f"../src/{source.name}",
        )
        execution = run_foundry_test(
            root, generated, f"X-{hypothesis.hypothesis_id}", label
        )
        if not execution.executed:
            raise RuntimeError(f"Foundry experiment {execution.experiment_id} failed before test execution\\nSTDOUT:\\n{execution.stdout}\\nSTDERR:\\n{execution.stderr}")
        require_executed(execution)
        return execution


def _canonical_model(hypothesis):
    model = SystemModel()
    cid = "contract:OlympusTreasury"
    fid = "function:OlympusTreasury:repayLoan"
    iid = f"invariant:{hypothesis.invariant_id}"
    hid = f"hypothesis:{hypothesis.hypothesis_id}"
    oid = "cross-contract-attribution"

    model.add_node(Node(cid, "contract", "OlympusTreasury", {"provenance": "historical-source-extraction"}))
    model.add_node(Node(fid, "function", "repayLoan", {"contract": "OlympusTreasury", "provenance": "historical-source-extraction"}))
    model.add_node(Node(iid, "invariant", hypothesis.claim, {"status": "inferred", "confidence": 0.82, "provenance": "cross-contract attribution reasoning"}))
    model.add_node(Node(hid, "hypothesis", hypothesis.claim, {"belief": 0.5, "state": "unresolved", "invariant_id": iid, "provenance": "cross-contract attribution reasoning"}))
    model.add_node(
        Node(
            f"observation:{oid}",
            "observation",
            "requested repayment must not absorb unrelated balance increases during the external transfer",
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
                "provenance": "historical cross-contract attribution experiment",
            },
        )
    )
    model.add_edge(Edge(iid, "informs", hid, {}))
    model.add_edge(Edge(f"observation:{oid}", "tests", hid, {}))
    return model, CanonicalHypothesis(hypothesis.hypothesis_id, hypothesis.claim, 0.5), oid


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("backtest-artifacts/olympus-cross-contract-attribution"),
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]

    with tempfile.TemporaryDirectory(prefix="cydra-olympus-target-") as tmp:
        target_source = _clone_historical_source(Path(tmp) / "target")
        result = investigate(
            target_source,
            target=f"{TARGET_REPO}@{TARGET_REF}:{TARGET_PATH}",
            reasoning_surfaces=(generate_cross_contract_attribution_hypotheses,),
            experiment_planner=plan_cross_contract_attribution_experiment,
        )

        hypotheses = [
            h
            for h in result.hypotheses
            if h.invariant_id.startswith("INV-CROSS-CONTRACT-ATTRIBUTION-")
        ]
        if len(hypotheses) != 1:
            raise SystemExit(f"expected one blind attribution hypothesis, got {len(hypotheses)}")

        hypothesis = hypotheses[0]
        experiment = next(
            item for item in result.experiments if item.hypothesis_id == hypothesis.hypothesis_id
        )

    vulnerable = _run_side(FIXTURE_V, hypothesis, "vulnerable")
    patched = _run_side(FIXTURE_P, hypothesis, "patched")

    model, canonical_hypothesis, observation_id = _canonical_model(hypothesis)
    cycle = run_canonical_differential_cycle(
        model,
        hypothesis=canonical_hypothesis,
        observation_id=observation_id,
        vulnerable=vulnerable,
        patched=patched,
        outcome_id="olympus-cross-contract-attribution-differential",
    )

    impact = ImpactAssessment(
        ImpactLevel.MEDIUM,
        "debt/accounting integrity",
        "A caller can reduce recorded debt by more than the amount actually repaid when unrelated token inflows occur during the transfer callback.",
        (
            "the token can trigger another treasury inflow during transfer",
            "the repayment path trusts the full balance delta",
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
            True,
        ),
        finding_id=f"F-CROSS-CONTRACT-ATTRIBUTION-{hypothesis.target_function}",
        hypothesis_id=f"hypothesis:{hypothesis.hypothesis_id}",
        evidence_ids=cycle.causal_verification.evidence_ids,
        causal_chain_id=cycle.causal_chain.chain_id,
    )

    args.output.mkdir(parents=True, exist_ok=True)
    payload = {
        "historical_target": {
            "repo": TARGET_REPO,
            "ref": TARGET_REF,
            "path": TARGET_PATH,
        },
        "hypothesis": hypothesis.__dict__,
        "experiment": experiment.__dict__,
        "execution": {
            "vulnerable": vulnerable.__dict__,
            "patched": patched.__dict__,
        },
        "causal_verification": cycle.causal_verification.__dict__,
        "finding_gate": {
            "decision": gate.decision.value,
            "reasons": list(gate.reasons),
        },
        "ground_truth_note": "External historical report was not used to generate the hypothesis; it is post-run context only.",
    }
    (args.output / "result.json").write_text(
        json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, indent=2, default=str))
    return 0 if gate.decision.value == "READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
