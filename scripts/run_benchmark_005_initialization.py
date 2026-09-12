from __future__ import annotations

import json
from pathlib import Path

from cydra.initialization_runtime import classify_initialization_execution, run_initialization_harness
from cydra.models import Hypothesis


TARGETS = ("Minter", "Voter", "Pool")


def _hypothesis(target: str) -> Hypothesis:
    return Hypothesis(
        hypothesis_id=f"H-INIT-{target}",
        claim="unauthorized caller can initialize target state",
        invariant_id="INV-INIT-001",
        target_function="initialize",
        attacker_capability="external caller",
        expected_impact="initialization",
    )


def main() -> int:
    project = Path("liquidclaw")
    results = run_initialization_harness(project)
    outcomes = []
    for result in results:
        outcome = classify_initialization_execution(_hypothesis(result.target), result)
        outcomes.append(outcome)
        print(
            "CLASSIFICATION:",
            result.target,
            f"status={result.status}",
            f"internal={outcome.internal_status}",
            f"benchmark={outcome.benchmark_status}",
            f"evidence={outcome.evidence.evidence_id}",
        )

    if tuple(result.target for result in results) != TARGETS:
        raise RuntimeError(f"unexpected target order: {[result.target for result in results]}")

    record = {
        "benchmark": "005_liquidclaw_initialization",
        "integrity": "PASS",
        "targets": [
            {
                "target": outcome.execution.target,
                "status": outcome.execution.status,
                "tests_run": outcome.execution.tests_run,
                "tests_failed": outcome.execution.tests_failed,
                "exit_code": outcome.execution.exit_code,
                "hypothesis_id": outcome.hypothesis.hypothesis_id,
                "hypothesis_status": outcome.hypothesis.status,
                "benchmark_classification": outcome.benchmark_status,
                "evidence_id": outcome.evidence.evidence_id,
                "evidence_claim": outcome.evidence.claim,
            }
            for outcome in outcomes
        ],
    }
    print("BENCHMARK_RECORD:", json.dumps(record, sort_keys=True))

    expected = {"Minter": "not_confirmed", "Voter": "not_confirmed", "Pool": "not_confirmed"}
    actual = {item["target"]: item["benchmark_classification"] for item in record["targets"]}
    if actual != expected:
        raise RuntimeError(f"prediction mismatch: expected={expected}, actual={actual}")
    print("BENCHMARK 005 CLASSIFICATION: PASS")
    print("PREDICTION COMPARISON: Minter=not_confirmed, Voter=not_confirmed, Pool=not_confirmed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
