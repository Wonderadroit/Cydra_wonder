from __future__ import annotations

import json
from pathlib import Path

from cydra.canonical_cycle import run_canonical_differential_cycle
from cydra.experiment_binding import bind_experiment
from cydra.finding import Finding
from cydra.finding_gate import FindingCandidate, evaluate_finding_graph
from cydra.finding_persistence import persist_finding
from cydra.foundry import classify_access_control_outcome, generate_access_control_test, require_executed, run_foundry_test, test_path_for
from cydra.impact import ImpactAssessment, ImpactLevel, ImpactScope, AttackerAccess, Exploitability, Repeatability, Recoverability
from cydra.pipeline import investigate
from cydra.solidity_model import parse_solidity
from cydra.solidity_system_model import project_contracts
from cydra.system_model_reasoning import materialize_authorization_observations, materialize_authorization_reasoning

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmarks" / "alchemix_missing_access_control"
FOUNDRY = BENCHMARK / "foundry"


def _bind_canonical_experiment(canonical_model, canonical_reasoning, generated_test: Path) -> dict:
    reasoning = canonical_reasoning[0]
    plans = materialize_authorization_observations(canonical_model, reasoning)
    hypothesis = next(h for h in reasoning.hypotheses if "setWhitelist" in h.statement and "alternate enforcement path" not in h.statement)
    observation_id = next(plan.observation_id for plan in plans if plan.observation_id in hypothesis.planning_predictions)
    target_function_id = next(
        node_id for node_id, node in canonical_model.nodes.items()
        if node.kind == "function" and node.label == "setWhitelist"
    )
    source = generated_test.read_text(encoding="utf-8")
    marker = f"// CYDRA-HYPOTHESIS: {hypothesis.hypothesis_id}"
    if marker not in source:
        source = marker + "\n" + source
        generated_test.write_text(source, encoding="utf-8")
    binding = bind_experiment(
        canonical_model,
        hypothesis_id=hypothesis.hypothesis_id,
        observation_id=observation_id,
        target_function_id=target_function_id,
        generated_source=source,
    )
    return {
        "hypothesis_id": binding.hypothesis_id,
        "observation_id": binding.observation_id,
        "target_function_id": binding.target_function_id,
        "source_marker": binding.source_marker,
    }


def main() -> int:
    source = BENCHMARK / "Target.sol"
    result = investigate(source, target="benchmark-001")
    hypothesis = next(h for h in result.hypotheses if h.hypothesis_id == "H-AUTH-setWhitelist")

    canonical_model = project_contracts(tuple(parse_solidity(source)))
    canonical_reasoning = materialize_authorization_reasoning(canonical_model)
    canonical_binding = None
    canonical_hypothesis = None
    canonical_observation_id = None

    vulnerable_test = generate_access_control_test(
        hypothesis,
        "../../src/Target.sol",
        "AlchemixAccessControlFixture",
        test_path_for(FOUNDRY, "generated/H_AUTH_setWhitelist_vulnerable.t.sol"),
    )
    patched_test = generate_access_control_test(
        hypothesis,
        "../../src/PatchedTarget.sol",
        "AlchemixAccessControlPatchedFixture",
        test_path_for(FOUNDRY, "generated/H_AUTH_setWhitelist_patched.t.sol"),
    )
    canonical_binding = _bind_canonical_experiment(canonical_model, canonical_reasoning, vulnerable_test)
    canonical_hypothesis = next(
        h for h in canonical_reasoning[0].hypotheses if h.hypothesis_id == canonical_binding["hypothesis_id"]
    )
    canonical_observation_id = canonical_binding["observation_id"]

    vulnerable = run_foundry_test(FOUNDRY, vulnerable_test, "X-H-AUTH-setWhitelist", "vulnerable")
    patched = run_foundry_test(FOUNDRY, patched_test, "X-H-AUTH-setWhitelist", "patched")
    require_executed(vulnerable)
    require_executed(patched)
    outcome = classify_access_control_outcome(hypothesis, vulnerable, patched)

    cycle = run_canonical_differential_cycle(
        canonical_model,
        hypothesis=canonical_hypothesis,
        observation_id=canonical_observation_id,
        vulnerable=vulnerable,
        patched=patched,
        outcome_id="benchmark-001-setWhitelist-differential",
    )
    impact = ImpactAssessment(
        ImpactLevel.HIGH,
        "privileged whitelist state",
        "an unauthorized caller can mutate privileged access-control state",
        ("unauthorized caller can reach setWhitelist",),
        cycle.causal_verification.evidence_ids,
        ImpactScope.PROTOCOL_WIDE, AttackerAccess.PERMISSIONLESS, Exploitability.DEMONSTRATED, Repeatability.REPEATABLE, Recoverability.IRREVERSIBLE,
    )
    finding_candidate = FindingCandidate(True, False, True, True, True, impact.assessed, True)
    gate = evaluate_finding_graph(
        canonical_model,
        candidate=finding_candidate,
        finding_id="F-AUTH-setWhitelist",
        hypothesis_id=f"hypothesis:{canonical_hypothesis.hypothesis_id}",
        evidence_ids=cycle.causal_verification.evidence_ids,
        causal_chain_id=cycle.causal_chain.chain_id,
    )

    persisted_finding = None
    if gate.decision.value == "READY":
        finding = Finding(
            "F-AUTH-setWhitelist",
            "Unauthorized setWhitelist access control",
            "An unauthorized caller can mutate privileged whitelist state through setWhitelist.",
            "HIGH",
            impact,
            (canonical_binding["target_function_id"],),
            cycle.causal_verification.evidence_ids,
            f"hypothesis:{canonical_hypothesis.hypothesis_id}",
            causal_chain_id=cycle.causal_chain.chain_id,
        )
        persist_finding(canonical_model, candidate=finding_candidate, finding=finding)
        persisted_finding = canonical_model.nodes[finding.finding_id].attributes

    package = {
        "canonical_reasoning": [
            {
                "invariant": item.invariant.__dict__,
                "hypotheses": [h.__dict__ for h in item.hypotheses],
                "protected_functions": item.protected_functions,
                "unprotected_functions": item.unprotected_functions,
            }
            for item in canonical_reasoning
        ],
        "canonical_binding": canonical_binding,
        "canonical_cycle": {
            "hypothesis": cycle.hypothesis.__dict__,
            "belief_update": cycle.belief_update.__dict__,
            "verification": cycle.verification.__dict__,
            "causal_chain": cycle.causal_chain.__dict__,
            "causal_verification": cycle.causal_verification.__dict__,
        },
        "finding_gate": {"decision": gate.decision.value, "reasons": list(gate.reasons)},
        "persisted_finding": persisted_finding,
        "hypothesis": outcome.hypothesis.__dict__,
        "vulnerable": vulnerable.__dict__,
        "patched": patched.__dict__,
        "evidence": [e.__dict__ for e in outcome.evidence],
    }
    print(json.dumps(package, indent=2, sort_keys=True, default=str))
    return 0 if outcome.hypothesis.status == "confirmed" and gate.decision.value == "READY" and persisted_finding is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
