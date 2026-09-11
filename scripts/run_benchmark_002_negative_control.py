from __future__ import annotations

import json
import shutil
from pathlib import Path

from cydra.foundry import generate_initialization_test, run_foundry_test
from cydra.pipeline import investigate

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmarks" / "wormhole_uninitialized"
SOURCE = BENCHMARK / "SafeTarget.sol"
FOUNDRY = BENCHMARK / "foundry"
TARGET = FOUNDRY / "SafeTarget.sol"
TEST = FOUNDRY / "SafeInitializationInvariant.t.sol"


def main() -> int:
    result = investigate(SOURCE)
    hypotheses = [h for h in result.hypotheses if h.invariant_id == "INV-INIT-001"]
    if len(hypotheses) != 1:
        raise AssertionError(f"expected exactly one initialization hypothesis, got {len(hypotheses)}")

    hypothesis = hypotheses[0]
    TARGET.write_text(SOURCE.read_text(encoding="utf-8"), encoding="utf-8")
    generated = generate_initialization_test(
        hypothesis,
        "./SafeTarget.sol",
        "WormholeInitializationFixture",
        TEST,
    )
    # Avoid relying on the benchmark's historical test contract name.
    source = generated.read_text(encoding="utf-8")
    source = source.replace(
        "contract CydraInitializationInvariantTest",
        "contract CydraSafeInitializationNegativeControlTest",
    )
    generated.write_text(source, encoding="utf-8")

    execution = run_foundry_test(FOUNDRY, generated, f"X-{hypothesis.hypothesis_id}-NEGATIVE-CONTROL", "safe")
    output = {
        "benchmark": "002-negative-control",
        "protocol": "safe initialization must not be confirmed",
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
