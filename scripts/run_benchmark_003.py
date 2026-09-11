from __future__ import annotations

import json
from pathlib import Path
import re

from cydra.foundry import generate_arithmetic_foundry_test
from cydra.pipeline import investigate
from scripts.probe_foundry_event_transport import probe_event_transport

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmarks" / "003_arithmetic_rounding"
SOURCE = BENCH / "Target.sol"
FOUNDRY = BENCH / "foundry"
GENERATED_TEST = FOUNDRY / "test" / "CydraArithmeticInvariant.t.sol"
BENCHMARK_003_HARNESS_BOUNDARY = "foundry-event-transport-probe"


def _assertion_lines(source: str) -> list[str]:
    return [
        line.strip()
        for line in source.splitlines()
        if re.search(r"\b(assert[A-Za-z]*|vm\.expectRevert)\s*\(", line)
    ]


def main() -> int:
    result = investigate(SOURCE, target="benchmark-003")
    arithmetic_hypotheses = [
        hypothesis
        for hypothesis in result.hypotheses
        if hypothesis.invariant_id.startswith("INV-ARITH-")
    ]

    extraction_fired = bool(arithmetic_hypotheses)
    arithmetic_hypothesis_ids = {hypothesis.hypothesis_id for hypothesis in arithmetic_hypotheses}
    arithmetic_experiments = [
        experiment
        for experiment in result.experiments
        if experiment.hypothesis_id in arithmetic_hypothesis_ids
    ]

    if not extraction_fired:
        raise SystemExit("Benchmark 003 reached the extraction boundary without an arithmetic hypothesis; stop before downstream stages.")
    if not arithmetic_experiments:
        raise SystemExit("Benchmark 003 reached the experiment boundary without an arithmetic experiment; stop before generator stages.")

    experiment = arithmetic_experiments[0]
    generated_source = generate_arithmetic_foundry_test(
        experiment,
        "../src/Target.sol:ArithmeticRoundingFixture",
        "../src/PatchedTarget.sol:ArithmeticRoundingFixture",
    )
    GENERATED_TEST.write_text(generated_source, encoding="utf-8")
    assertion_lines = _assertion_lines(generated_source)
    probe = probe_event_transport(FOUNDRY, GENERATED_TEST)

    payload = {
        "benchmark": "003",
        "class": "arithmetic-rounding",
        "harness_boundary": BENCHMARK_003_HARNESS_BOUNDARY,
        "experiment": experiment.__dict__,
        "generated_foundry_test": generated_source,
        "assertion_lines": assertion_lines,
        "probe": probe,
        "downstream": {
            "measurement_production": "NOT_REACHED",
            "evidence_schema": "NOT_REACHED",
            "classifier": "NOT_REACHED",
        },
    }
    print(json.dumps(payload, indent=2, default=list))

    raise SystemExit(
        "Benchmark 003 harness boundary reached: Foundry event transport probe recorded; "
        "stop before measurement production."
    )


if __name__ == "__main__":
    raise SystemExit(main())
