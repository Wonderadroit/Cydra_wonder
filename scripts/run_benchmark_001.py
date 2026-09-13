from __future__ import annotations

import json
from pathlib import Path

from cydra.experiment_binding import bind_experiment
from cydra.foundry import classify_access_control_outcome, generate_access_control_test, require_executed, run_foundry_test, test_path_for
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

    vulnerable = run_foundry_test(FOUNDRY, vulnerable_test, "X-H-AUTH-setWhitelist", "vulnerable")
    patched = run_foundry_test(FOUNDRY, patched_test, "X-H-AUTH-setWhitelist", "patched")
    require_executed(vulnerable)
    require_executed(patched)
    outcome = classify_access_control_outcome(hypothesis, vulnerable, patched)

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
        "hypothesis": outcome.hypothesis.__dict__,
        "vulnerable": vulnerable.__dict__,
        "patched": patched.__dict__,
        "evidence": [e.__dict__ for e in outcome.evidence],
    }
    print(json.dumps(package, indent=2, sort_keys=True, default=str))
    return 0 if outcome.hypothesis.status == "confirmed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
