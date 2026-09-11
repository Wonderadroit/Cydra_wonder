from __future__ import annotations

import json
from pathlib import Path

from cydra.pipeline import investigate

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmarks" / "003_arithmetic_rounding"
SOURCE = BENCH / "Target.sol"
BENCHMARK_003_HARNESS_BOUNDARY = "experiment"


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

    payload = {
        "benchmark": "003",
        "class": "arithmetic-rounding",
        "harness_boundary": BENCHMARK_003_HARNESS_BOUNDARY,
        "prediction": {
            "extraction": "YES",
            "hypothesis_schema": "YES",
            "experiment_schema": "YES",
            "evidence_schema": "YES",
            "classifier": "YES",
        },
        "actual": {
            "extraction": "YES" if extraction_fired else "NO",
            "hypothesis_schema": "NOT_REACHED" if not extraction_fired else "YES",
            "experiment_schema": "NOT_REACHED" if not extraction_fired else "YES" if arithmetic_experiments else "NO",
            "experiment_artifact": "NOT_REACHED" if not arithmetic_experiments else "CAPTURED",
            "foundry_test": "NOT_DECLARED_IN_ENGINE",
            "evidence_schema": "NOT_REACHED",
            "classifier": "NOT_REACHED",
        },
        "prediction_falsified": not extraction_fired,
        "contracts_extracted": [contract.name for contract in result.contracts],
        "functions_extracted": [
            {
                "name": function.name,
                "visibility": function.visibility,
                "writes": list(function.writes),
            }
            for contract in result.contracts
            for function in contract.functions
        ],
        "invariants": [invariant.__dict__ for invariant in result.invariants],
        "hypotheses": [hypothesis.__dict__ for hypothesis in result.hypotheses],
        "experiments": [experiment.__dict__ for experiment in arithmetic_experiments],
    }
    print(json.dumps(payload, indent=2, default=list))

    if not extraction_fired:
        raise SystemExit(
            "Benchmark 003 reached the extraction boundary without an arithmetic hypothesis; stop before downstream stages."
        )
    if not arithmetic_experiments:
        raise SystemExit(
            "Benchmark 003 reached the hypothesis boundary without an arithmetic experiment; stop before downstream stages."
        )

    raise SystemExit(
        "Benchmark 003 harness boundary reached: experiment artifact captured; "
        "no arithmetic Foundry generator is declared yet, so stop before evidence/classifier."
    )


if __name__ == "__main__":
    raise SystemExit(main())
