from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from cydra.canonical_cycle import run_canonical_differential_cycle
from cydra.finding_gate import FindingCandidate, evaluate_finding_graph
from cydra.hypothesis_selection import select_next_hypothesis
from cydra.hypotheses import Hypothesis as CanonicalHypothesis
from cydra.impact import ImpactAssessment, ImpactLevel
from cydra.pipeline import investigate
from cydra.system_model import Edge, Node, SystemModel
from cydra.solidity_model import parse_solidity

from scripts.run_benchmark_005_blind import run_initialization
from scripts.run_benchmark_021_unfamiliar_control_flow import (
    TARGET_REPO,
    TARGET_REF,
    TARGET_PATH,
    clone_target,
    run_target,
    patch_target,
)

def canonical_model(hypothesis):
    model = SystemModel()
    function_id = f"function:Prime:{hypothesis.target_function}"
    invariant_id = f"invariant:{hypothesis.invariant_id}"
    hypothesis_id = f"hypothesis:{hypothesis.hypothesis_id}"
    observation_id = "continue-bypasses-progress"
    model.add_node(Node("contract:Prime", "contract", "Prime", {"provenance": "pinned historical source"}))
    model.add_node(Node(function_id, "function", hypothesis.target_function, {"provenance": "pinned historical source"}))
    model.add_node(Node(invariant_id, "invariant", hypothesis.claim, {"status": "inferred", "confidence": 0.87}))
    model.add_node(Node(hypothesis_id, "hypothesis", hypothesis.claim, {"belief": 0.5}))
    model.add_node(Node(
        f"observation:{observation_id}", "observation",
        "a previously processed user is supplied before a still-unprocessed user",
        {"status": "planned", "hypothesis_id": hypothesis_id, "target_function_id": function_id,
         "binding_status": "bound",
         "experiment_binding": {"hypothesis_id": hypothesis_id,
                                "observation_id": f"observation:{observation_id}",
                                "target_function_id": function_id}},
    ))
    model.add_edge(Edge(invariant_id, "informs", hypothesis_id, {}))
    model.add_edge(Edge(f"observation:{observation_id}", "tests", hypothesis_id, {}))
    return model, CanonicalHypothesis(hypothesis.hypothesis_id, hypothesis.claim, 0.5), observation_id

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("backtest-artifacts/iterative-blind-control-flow"))
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="cydra-venus-iterative-") as tmp:
        target = clone_target(Path(tmp) / "target")
        source = target / TARGET_PATH

        # Strict blind: only the target source is supplied to the normal pipeline.
        investigation = investigate(source, target=f"{TARGET_REPO}@{TARGET_REF}:{TARGET_PATH}")
        experiments = {e.hypothesis_id: e for e in investigation.experiments}

        first = select_next_hypothesis(
            investigation.hypotheses, investigation.invariants, investigation.experiments
        )

        # The first choice is evidence, not an oracle: execute exactly what CYDRA
        # selected, then use the measured outcome to decide whether it remains viable.
        if first.hypothesis.invariant_id != "INV-INIT-001":
            raise SystemExit(
                "unexpected first hypothesis for this observed target: "
                + first.hypothesis.hypothesis_id
            )

        contract = next(c for c in investigation.contracts if c.name == "Prime")
        init_experiment = experiments[first.hypothesis.hypothesis_id]
        _, init_execution, init_outcome = run_initialization(
            target, first.hypothesis, init_experiment, contract
        )
        if not init_execution.executed:
            raise RuntimeError("initialization hypothesis was not executable")

        # A non-confirming initialization result is a real observation that
        # removes that candidate from the next selection round.
        if init_outcome.benchmark_status == "confirmed":
            raise SystemExit("initialization hypothesis unexpectedly confirmed; do not treat it as a false-positive rejection")

        excluded = (first.hypothesis.hypothesis_id,)
        second = select_next_hypothesis(
            investigation.hypotheses,
            investigation.invariants,
            investigation.experiments,
            excluded_hypothesis_ids=excluded,
        )
        hypothesis = second.hypothesis
        if not hypothesis.invariant_id.startswith("INV-CONTROL-FLOW-"):
            raise SystemExit(
                "reselection did not advance to the control-flow hypothesis: "
                + hypothesis.hypothesis_id + "/" + hypothesis.target_function
            )

        experiment = experiments[hypothesis.hypothesis_id]
        vulnerable = run_target(target, "vulnerable")

    with tempfile.TemporaryDirectory(prefix="cydra-venus-iterative-patched-") as tmp:
        target = clone_target(Path(tmp) / "target")
        patch_target(target)
        patched = run_target(target, "patched")

    with tempfile.TemporaryDirectory(prefix="cydra-venus-iterative-repro-v-") as tmp:
        target = clone_target(Path(tmp) / "target")
        independent_vulnerable = run_target(target, "independent-vulnerable")

    with tempfile.TemporaryDirectory(prefix="cydra-venus-iterative-repro-p-") as tmp:
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
        outcome_id="iterative-control-flow-differential",
    )
    reproduction_verified = independent_vulnerable["status"] == "FAIL" and independent_patched["status"] == "PASS"
    impact = ImpactAssessment(
        ImpactLevel.MEDIUM,
        "score-update availability",
        "A reachable already-processed element can prevent updateScores from advancing, exhausting gas and preventing later users in the same batch from receiving their update.",
        ("one supplied user is already processed", "another supplied user remains pending"),
        cycle.causal_verification.evidence_ids,
    )
    gate = evaluate_finding_graph(
        model,
        candidate=FindingCandidate(
            True, False, True, True,
            cycle.causal_verification.state.value == "verified",
            impact.assessed, reproduction_verified,
        ),
        finding_id=f"F-ITERATIVE-CONTROL-FLOW-{hypothesis.target_function}",
        hypothesis_id=f"hypothesis:{hypothesis.hypothesis_id}",
        evidence_ids=cycle.causal_verification.evidence_ids,
        causal_chain_id=cycle.causal_chain.chain_id,
    )
    payload = {
        "target": {"repo": TARGET_REPO, "ref": TARGET_REF, "path": TARGET_PATH},
        "first_selection": first.hypothesis.__dict__,
        "first_execution": init_execution.__dict__,
        "first_classification": init_outcome.__dict__,
        "excluded_after_evidence": list(excluded),
        "second_selection": {"hypothesis": hypothesis.__dict__, "score": second.score},
        "experiment": experiment.__dict__,
        "vulnerable": vulnerable,
        "patched": patched,
        "causal_verification": cycle.causal_verification.__dict__,
        "independent_vulnerable": independent_vulnerable,
        "independent_patched": independent_patched,
        "reproduction_verified": reproduction_verified,
        "finding_gate": gate.decision.value,
        "boundary": "strict blind initial selection, actual pinned Venus execution for the selected control-flow hypothesis, isolated causal patch, and independent reproduction.",
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "result.json").write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))
    return 0 if gate.decision.value == "READY" else 1

if __name__ == "__main__":
    raise SystemExit(main())
