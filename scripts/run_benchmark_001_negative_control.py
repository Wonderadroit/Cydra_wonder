from __future__ import annotations

import json
from pathlib import Path

from cydra.foundry import generate_access_control_test, run_foundry_test
from cydra.pipeline import investigate

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmarks" / "alchemix_missing_access_control"
SOURCE = BENCHMARK / "SafeTarget.sol"
FOUNDRY = BENCHMARK / "foundry"
TARGET = FOUNDRY / "SafeAuthorizationTarget.sol"
TEST = FOUNDRY / "SafeAuthorizationInvariant.t.sol"


def main() -> int:
    result = investigate(SOURCE)
    hypotheses = [h for h in result.hypotheses if h.invariant_id == "INV-AUTH-001"]
    if len(hypotheses) != 1:
        raise AssertionError(f"expected exactly one authorization hypothesis, got {len(hypotheses)}")

    hypothesis = hypotheses[0]
    TARGET.write_text(SOURCE.read_text(encoding="utf-8"), encoding="utf-8")
    generated = generate_access_control_test(
        hypothesis,
        "./SafeAuthorizationTarget.sol",
        "AlchemixAccessControlSafeFixture",
        TEST,
    )
    execution = run_foundry_test(
        FOUNDRY,
        generated,
        f"X-{hypothesis.hypothesis_id}-AUTH-NEGATIVE-CONTROL",
        "safe",
    )

    output = {
        "benchmark": "001-negative-control",
        "protocol": "safe authorization must not be confirmed",
        "hypothesis": hypothesis.__dict__,
        "execution": execution.__dict__,
        "result": "not_confirmed" if execution.passed else "FAILURE_RECORDED",
    }
    print(json.dumps(output, indent=2, default=str))

    # Deliberately do not modify CYDRA if this fails. A failure is the result
    # to record and investigate after this run.
    return 0 if execution.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
