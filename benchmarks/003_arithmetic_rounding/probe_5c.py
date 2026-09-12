from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(SCRIPTS))

from probe_foundry_file_transport import probe_file_transport
from cydra.foundry import (
    ExecutionResult,
    classify_access_control_outcome,
    classify_arithmetic_outcome,
)
from cydra.models import Evidence, Hypothesis


PROJECT = REPO_ROOT / "benchmarks/003_arithmetic_rounding/foundry"
TEST = PROJECT / "test/CydraArithmeticInvariant.t.sol"


def _execution(status: str) -> ExecutionResult:
    return ExecutionResult(
        "X-H-ARITH-quoteMint",
        "benchmark-003",
        ("probe",),
        0 if status == "PASS" else 1,
        True,
        1,
        0 if status == "PASS" else 1,
        status,
        "",
        "",
    )


def _hypothesis() -> Hypothesis:
    return Hypothesis(
        "H-ARITH-quoteMint",
        "quoteMint may return a value above the exact floor because the arithmetic path rounds upward.",
        "INV-ARITH-001",
        "quoteMint",
        "arithmetic boundary input that exposes rounding drift",
        "quoted value exceeds the exact floor by at least one unit",
    )


def main() -> int:
    transport = probe_file_transport(PROJECT, TEST)
    if transport["classification"] != "CONFIRMED":
        print(json.dumps({"prediction": "5C", "classification": "UNMEASURABLE", "transport": transport}, indent=2))
        return 1

    runtime_payload = transport["measurement_payload"]
    positive_evidence = Evidence(
        "E-EXEC-H-ARITH-quoteMint-ARITHMETIC",
        "execution",
        "Arithmetic execution measurements transported from executed Solidity.",
        "benchmark-003-vulnerable+patched",
        "quoteMint",
        {
            "observed": runtime_payload["observed"],
            "referenceValue": runtime_payload["referenceValue"],
            "patched": runtime_payload["patched"],
        },
        "static_plus_execution",
    )

    positive = classify_arithmetic_outcome(
        _hypothesis(),
        positive_evidence,
        _execution("PASS"),
        _execution("PASS"),
    )

    negative_evidence = Evidence(
        "E-NEG-5C-ARITHMETIC",
        "execution",
        "Arithmetic negative control with populated measurements but no numerical differential.",
        "benchmark-003-negative-control",
        "quoteMint",
        {"observed": 1, "referenceValue": 1, "patched": 1},
        "static_plus_execution",
    )
    negative = classify_arithmetic_outcome(
        _hypothesis(),
        negative_evidence,
        _execution("FAIL"),
        _execution("PASS"),
    )

    legacy = classify_access_control_outcome(_hypothesis(), _execution("FAIL"), _execution("PASS"))

    result = {
        "prediction": "5C",
        "classification": "CONFIRMED"
        if positive.hypothesis.status == "confirmed"
        and negative.hypothesis.status == "proposed"
        and legacy.hypothesis.status == "confirmed"
        else "FALSIFIED",
        "routing_criterion": "Evidence.payload present + Evidence.source_verification present + required arithmetic fields",
        "positive": {
            "payload": positive_evidence.payload,
            "status_fields": [positive.vulnerable.status, positive.patched.status],
            "classification": positive.hypothesis.status,
            "measurement_rule": "observed > referenceValue AND patched == referenceValue",
            "payload_source": "5A-Transport-B runtime file payload",
        },
        "negative_control": {
            "payload": negative_evidence.payload,
            "status_fields": [negative.vulnerable.status, negative.patched.status],
            "classification": negative.hypothesis.status,
            "reason": "no numerical differential; observed == referenceValue and patched == referenceValue",
        },
        "legacy_status_control": {
            "status_fields": [legacy.vulnerable.status, legacy.patched.status],
            "classification": legacy.hypothesis.status,
        },
        "transport": {
            "classification": transport["classification"],
            "measurement_payload": runtime_payload,
        },
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["classification"] == "CONFIRMED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
