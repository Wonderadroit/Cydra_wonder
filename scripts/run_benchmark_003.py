from __future__ import annotations

import json
from pathlib import Path
import re

from cydra.foundry import run_foundry_test
from cydra.models import Evidence
from cydra.pipeline import investigate
from cydra.structural_arithmetic_execution import (
    extract_positive_offset_division,
    generate_structural_arithmetic_test,
)

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmarks" / "003_arithmetic_rounding"
SOURCE = BENCH / "Target.sol"
FOUNDRY = BENCH / "foundry"
GENERATED_TEST = FOUNDRY / "test" / "CydraArithmeticInvariant.t.sol"
BENCHMARK_003_HARNESS_BOUNDARY = "evidence"


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
        if hypothesis.invariant_id == "INV-ARITH-001"
    ]
    if not arithmetic_hypotheses:
        raise SystemExit("Benchmark 003 reached extraction without a structural arithmetic hypothesis.")

    arithmetic_hypothesis_ids = {hypothesis.hypothesis_id for hypothesis in arithmetic_hypotheses}
    arithmetic_experiments = [
        experiment
        for experiment in result.experiments
        if experiment.hypothesis_id in arithmetic_hypothesis_ids
    ]
    if not arithmetic_experiments:
        raise SystemExit("Benchmark 003 reached extraction without a structural arithmetic experiment.")

    hypothesis = arithmetic_hypotheses[0]
    experiment = arithmetic_experiments[0]
    shape = extract_positive_offset_division(result.contracts[0], hypothesis.target_function)
    if shape is None:
        raise SystemExit("Benchmark 003 structural arithmetic hypothesis could not be reconstructed into an executable shape.")

    generated_path = generate_structural_arithmetic_test(
        hypothesis,
        result.contracts[0],
        "../src/Target.sol",
        "../src/PatchedTarget.sol",
        "ArithmeticRoundingFixture",
        "ArithmeticRoundingFixture",
        GENERATED_TEST,
    )
    generated_source = generated_path.read_text(encoding="utf-8")
    execution = run_foundry_test(
        FOUNDRY,
        GENERATED_TEST,
        experiment.experiment_id,
        "benchmark-003-vulnerable+patched",
    )

    execution_evidence = Evidence(
        f"E-EXEC-{experiment.hypothesis_id}-ARITHMETIC",
        "execution",
        f"Structural arithmetic differential test: status={execution.status}, executed={execution.executed}, tests_run={execution.tests_run}, tests_failed={execution.tests_failed}, exit={execution.exit_code}.",
        " ".join(execution.command),
        execution.target,
    )

    payload = {
        "benchmark": "003",
        "class": "arithmetic-rounding",
        "harness_boundary": BENCHMARK_003_HARNESS_BOUNDARY,
        "hypothesis": hypothesis.__dict__,
        "experiment": experiment.__dict__,
        "shape": shape.__dict__,
        "generated_foundry_test": generated_source,
        "assertion_lines": _assertion_lines(generated_source),
        "execution": {
            "tests_run": execution.tests_run,
            "tests_failed": execution.tests_failed,
            "status": execution.status,
            "exit_code": execution.exit_code,
        },
        "evidence": execution_evidence.__dict__,
        "downstream": {"classifier": "NOT_REACHED"},
    }
    print(json.dumps(payload, indent=2, default=list))
    print("Benchmark 003 harness boundary reached: structural arithmetic execution evidence recorded; stop before classifier.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
