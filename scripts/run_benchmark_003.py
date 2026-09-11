from __future__ import annotations

import json
from pathlib import Path

from cydra.pipeline import investigate

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmarks" / "003_arithmetic_rounding"
SOURCE = BENCH / "Target.sol"


def main() -> int:
    result = investigate(SOURCE, target="benchmark-003")
    arithmetic_hypotheses = [
        hypothesis
        for hypothesis in result.hypotheses
        if hypothesis.invariant_id.startswith("INV-ARITH-")
    ]

    extraction_fired = bool(arithmetic_hypotheses)
    payload = {
        "benchmark": "003",
        "class": "arithmetic-rounding",
        "prediction": {
            "extraction": "YES",
            "hypothesis_schema": "YES",
            "experiment_schema": "YES",
            "evidence_schema": "YES",
            "classifier": "YES",
        },
        "actual": {
            "extraction": "YES" if extraction_fired else "NO",
            "hypothesis_schema": "NOT_REACHED" if not extraction_fired else "NOT_TESTED",
            "experiment_schema": "NOT_REACHED" if not extraction_fired else "NOT_TESTED",
            "evidence_schema": "NOT_REACHED" if not extraction_fired else "NOT_TESTED",
            "classifier": "NOT_REACHED" if not extraction_fired else "NOT_TESTED",
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
    }
    print(json.dumps(payload, indent=2, default=list))

    if extraction_fired:
        raise SystemExit(
            "Benchmark 003 reached an arithmetic hypothesis unexpectedly; stop and compare before extending the engine."
        )

    print("BENCHMARK_003_BOUNDARY: arithmetic extraction did not fire; no reasoning-engine changes made.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
