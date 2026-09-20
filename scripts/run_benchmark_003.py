from __future__ import annotations

import json
from pathlib import Path
import re

from cydra.canonical_cycle import run_canonical_differential_cycle
from cydra.foundry import (
    classify_experiment_outcome,
    require_executed,
    run_foundry_test,
    test_path_for,
)
from cydra.finding import Finding
from cydra.finding_gate import FindingCandidate, evaluate_finding_graph
from cydra.finding_persistence import persist_finding
from cydra.hypotheses import Hypothesis as CanonicalHypothesis
from cydra.impact import ImpactAssessment, ImpactLevel
from cydra.models import Evidence
from cydra.pipeline import investigate
from cydra.solidity_model import parse_solidity
from cydra.structural_arithmetic_execution import (
    extract_positive_offset_division,
    generate_structural_arithmetic_security_test,
)
from cydra.system_model import Edge, Node, SystemModel


ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmarks" / "003_arithmetic_rounding"
SOURCE = BENCH / "Target.sol"
PATCHED = BENCH / "PatchedTarget.sol"
FOUNDRY = BENCH / "foundry"
VULNERABLE_TEST = test_path_for(FOUNDRY, "generated/CydraArithmeticInvariantVulnerable.t.sol")
PATCHED_TEST = test_path_for(FOUNDRY, "generated/CydraArithmeticInvariantPatched.t.sol")


def _assertion_lines(source: str) -> list[str]:
    return [
        line.strip()
        for line in source.splitlines()
        if re.search(r"\b(assert[A-Za-z]*|vm\.expectRevert)\s*\(", line)
    ]


def _canonical_model(hypothesis, contract_name: str) -> tuple[SystemModel, CanonicalHypothesis, str]:
    model = SystemModel()
    contract_id = f"contract:{contract_name}"
    function_id = f"function:{contract_name}:{hypothesis.target_function}"
    invariant_id = "invariant:INV-ARITH-001"
    hypothesis_id = f"hypothesis:{hypothesis.hypothesis_id}"
    observation_id = f"OBS-ARITH-{contract_name}-{hypothesis.target_function}"

    model.add_node(Node(contract_id, "contract", contract_name, {"provenance": "solidity_model"}))
    model.add_node(
        Node(
            function_id,
            "function",
            hypothesis.target_function,
            {"contract": contract_name, "visibility": "external", "provenance": "solidity_model"},
        )
    )
    model.add_node(
        Node(
            invariant_id,
            "invariant",
            "Integer division must preserve the intended rounding direction; a positive offset before division must not raise the result above the exact floor.",
            {
                "status": "inferred",
                "confidence": 0.80,
                "provenance": "structural arithmetic rule; positive-offset numerator followed by integer division",
            },
        )
    )
    model.add_node(
        Node(
            hypothesis_id,
            "hypothesis",
            hypothesis.claim,
            {
                "belief": 0.5,
                "state": "unresolved",
                "invariant_id": invariant_id,
                "provenance": "structural arithmetic reasoning",
            },
        )
    )
    model.add_node(
        Node(
            f"observation:{observation_id}",
            "observation",
            f"Execute {hypothesis.target_function} with a discriminating boundary input and test the exact-floor invariant.",
            {
                "status": "planned",
                "target_function_id": function_id,
                "provenance": "structural arithmetic experiment",
            },
        )
    )
    model.add_edge(Edge(invariant_id, "informs", hypothesis_id, {"provenance": "structural arithmetic reasoning"}))
    model.add_edge(Edge(f"observation:{observation_id}", "targets", invariant_id, {"provenance": "structural arithmetic reasoning"}))
    model.add_edge(Edge(f"observation:{observation_id}", "tests", hypothesis_id, {"provenance": "structural arithmetic reasoning"}))

    canonical_hypothesis = CanonicalHypothesis(
        hypothesis.hypothesis_id,
        hypothesis.claim,
        0.5,
    )
    return model, canonical_hypothesis, observation_id


def main() -> int:
    result = investigate(SOURCE, target="benchmark-003")
    arithmetic_hypotheses = [
        hypothesis
        for hypothesis in result.hypotheses
        if hypothesis.invariant_id == "INV-ARITH-001"
    ]
    if not arithmetic_hypotheses:
        raise SystemExit("Benchmark 003 reached extraction without a structural arithmetic hypothesis.")

    hypothesis = arithmetic_hypotheses[0]
    experiment = next(
        (
            item
            for item in result.experiments
            if item.hypothesis_id == hypothesis.hypothesis_id
        ),
        None,
    )
    if experiment is None:
        raise SystemExit("Benchmark 003 reached extraction without a structural arithmetic experiment.")

    contract = next(
        (
            item
            for item in result.contracts
            if any(fn.name == hypothesis.target_function for fn in item.functions)
        ),
        None,
    )
    if contract is None:
        raise SystemExit(f"No analyzed contract contains target function {hypothesis.target_function!r}.")

    shape = extract_positive_offset_division(contract, hypothesis.target_function)
    if shape is None:
        raise SystemExit(
            "Benchmark 003 structural arithmetic hypothesis could not be reconstructed into an executable shape."
        )

    vulnerable_path = generate_structural_arithmetic_security_test(
        hypothesis,
        contract,
        "../src/Target.sol",
        "ArithmeticRoundingFixture",
        VULNERABLE_TEST,
        experiment=experiment,
    )
    patched_path = generate_structural_arithmetic_security_test(
        hypothesis,
        contract,
        "../src/PatchedTarget.sol",
        "ArithmeticRoundingFixture",
        PATCHED_TEST,
        experiment=experiment,
    )

    vulnerable = run_foundry_test(
        FOUNDRY,
        vulnerable_path,
        experiment.experiment_id,
        "benchmark-003-vulnerable",
    )
    patched = run_foundry_test(
        FOUNDRY,
        patched_path,
        experiment.experiment_id,
        "benchmark-003-patched",
    )
    require_executed(vulnerable)
    require_executed(patched)

    outcome = classify_experiment_outcome(hypothesis, vulnerable, patched)
    canonical_model, canonical_hypothesis, observation_id = _canonical_model(
        hypothesis,
        contract.name,
    )
    cycle = run_canonical_differential_cycle(
        canonical_model,
        hypothesis=canonical_hypothesis,
        observation_id=observation_id,
        vulnerable=vulnerable,
        patched=patched,
        outcome_id="benchmark-003-arithmetic-differential",
    )

    impact = ImpactAssessment(
        ImpactLevel.MEDIUM,
        "mint/share quote",
        "the vulnerable arithmetic path returns more units than the exact-floor invariant permits for a discriminating input",
        ("caller controls the arithmetic input",),
        cycle.causal_verification.evidence_ids,
    )
    finding_candidate = FindingCandidate(
        True,
        False,
        True,
        True,
        cycle.causal_verification.state.value == "verified",
        impact.assessed,
        True,
    )
    gate = evaluate_finding_graph(
        canonical_model,
        candidate=finding_candidate,
        finding_id="F-ARITH-quoteMint",
        hypothesis_id=f"hypothesis:{hypothesis.hypothesis_id}",
        evidence_ids=cycle.causal_verification.evidence_ids,
        causal_chain_id=cycle.causal_chain.chain_id,
    )

    persisted_finding = None
    if gate.decision.value == "READY":
        finding = Finding(
            "F-ARITH-quoteMint",
            "Arithmetic rounding violates exact-floor invariant",
            "The externally callable arithmetic path returns above the exact integer floor for a discriminating caller-controlled input.",
            "MEDIUM",
            impact,
            (f"function:{contract.name}:{hypothesis.target_function}",),
            cycle.causal_verification.evidence_ids,
            f"hypothesis:{hypothesis.hypothesis_id}",
            causal_chain_id=cycle.causal_chain.chain_id,
        )
        persist_finding(canonical_model, candidate=finding_candidate, finding=finding)
        persisted_finding = canonical_model.nodes[finding.finding_id].attributes

    execution_evidence = Evidence(
        f"E-EXEC-{hypothesis.hypothesis_id}-ARITHMETIC",
        "execution",
        f"Structural arithmetic security test: vulnerable={vulnerable.status}, patched={patched.status}, executed={vulnerable.executed and patched.executed}, vulnerable_tests_failed={vulnerable.tests_failed}, patched_tests_failed={patched.tests_failed}.",
        " ".join(vulnerable.command),
        vulnerable.target,
    )

    payload = {
        "benchmark": "003",
        "class": "arithmetic-rounding",
        "harness_boundary": "finding",
        "hypothesis": hypothesis.__dict__,
        "experiment": experiment.__dict__,
        "shape": shape.__dict__,
        "generated_assertions": {
            "vulnerable": _assertion_lines(vulnerable_path.read_text(encoding="utf-8")),
            "patched": _assertion_lines(patched_path.read_text(encoding="utf-8")),
        },
        "execution": {
            "vulnerable": vulnerable.__dict__,
            "patched": patched.__dict__,
        },
        "outcome": {
            "hypothesis": outcome.hypothesis.__dict__,
            "evidence": [item.__dict__ for item in outcome.evidence],
        },
        "canonical_cycle": {
            "verification": cycle.verification.__dict__,
            "causal_chain": cycle.causal_chain.__dict__,
            "causal_verification": cycle.causal_verification.__dict__,
        },
        "finding_gate": {
            "decision": gate.decision.value,
            "reasons": list(gate.reasons),
        },
        "persisted_finding": persisted_finding,
        "evidence_record": execution_evidence.__dict__,
    }
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))

    return 0 if (
        outcome.hypothesis.status == "confirmed"
        and gate.decision.value == "READY"
        and persisted_finding is not None
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
