from __future__ import annotations

import json
from pathlib import Path

from cydra.foundry import classify_access_control_outcome, generate_access_control_test, require_executed, run_foundry_test, test_path_for
from cydra.pipeline import investigate
from cydra.solidity_model import parse_solidity
from cydra.solidity_system_model import project_contracts
from cydra.system_model_reasoning import materialize_authorization_reasoning


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmarks" / "alchemix_missing_access_control"
FOUNDRY = BENCHMARK / "foundry"


def main() -> int:
    source = BENCHMARK / "Target.sol"
    result = investigate(source, target="benchmark-001")
    hypothesis = next(h for h in result.hypotheses if h.hypothesis_id == "H-AUTH-setWhitelist")

    # Canonical path is observationally separate from the frozen legacy
    # benchmark result. It proves that the real Solidity target can traverse
    # parse -> SystemModel -> invariant -> hypothesis without importing the
    # legacy class-specific conclusion.
    canonical_model = project_contracts(tuple(parse_solidity(source)))
    canonical_reasoning = materialize_authorization_reasoning(canonical_model)

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
        "hypothesis": outcome.hypothesis.__dict__,
        "vulnerable": vulnerable.__dict__,
        "patched": patched.__dict__,
        "evidence": [e.__dict__ for e in outcome.evidence],
    }
    print(json.dumps(package, indent=2, sort_keys=True, default=str))
    return 0 if outcome.hypothesis.status == "confirmed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
