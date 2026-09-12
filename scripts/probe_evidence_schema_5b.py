from __future__ import annotations

import json
import sys
from dataclasses import asdict, fields
from pathlib import Path

from cydra.models import Evidence
from probe_foundry_file_transport import probe_file_transport


REQUIRED_PAYLOAD_KEYS = ("observed", "referenceValue", "patched")
EXPECTED_VERIFICATION = "static_plus_execution"


def probe_evidence_schema(project_dir: str | Path, test_path: str | Path) -> dict[str, object]:
    transport = probe_file_transport(project_dir, test_path)
    if transport["classification"] != "CONFIRMED":
        return {
            "prediction": "5B",
            "classification": "UNMEASURABLE",
            "transport_classification": transport["classification"],
            "reason": "The confirmed 5A-Transport-B predecessor artifact was not available.",
        }

    payload = transport["measurement_payload"]
    if not isinstance(payload, dict):
        return {
            "prediction": "5B",
            "classification": "FALSIFIED",
            "reason": "Transport reported CONFIRMED but did not provide a structured measurement payload.",
        }

    authorization = Evidence(
        "E-MODEL-authorization",
        "model",
        "Authorization model evidence.",
        "benchmark-001",
        "authorization",
    )
    initialization = Evidence(
        "E-MODEL-initialization",
        "model",
        "Initialization model evidence.",
        "benchmark-002",
        "initialization",
    )
    arithmetic = Evidence(
        "E-EXEC-H-ARITH-quoteMint-ARITHMETIC",
        "execution",
        "Arithmetic execution measurements transported from executed Solidity.",
        "benchmark-003-vulnerable+patched",
        "quoteMint",
        {key: payload[key] for key in REQUIRED_PAYLOAD_KEYS},
        EXPECTED_VERIFICATION,
    )

    schema_fields = tuple(field.name for field in fields(Evidence))
    same_dataclass = all(type(item) is Evidence for item in (authorization, initialization, arithmetic))
    same_schema_fields = all(tuple(field.name for field in fields(item)) == schema_fields for item in (authorization, initialization, arithmetic))
    arithmetic_payload = arithmetic.payload
    payload_present = isinstance(arithmetic_payload, dict) and all(key in arithmetic_payload for key in REQUIRED_PAYLOAD_KEYS)
    payload_values_structured = payload_present and all(
        isinstance(arithmetic_payload[key], int) and not isinstance(arithmetic_payload[key], bool)
        for key in REQUIRED_PAYLOAD_KEYS
    )
    verification_preserved = arithmetic.source_verification == EXPECTED_VERIFICATION
    no_subclasses = same_dataclass

    classification = (
        "CONFIRMED"
        if no_subclasses and same_schema_fields and payload_present and payload_values_structured and verification_preserved
        else "FALSIFIED"
    )

    return {
        "prediction": "5B",
        "classification": classification,
        "schema_fields": list(schema_fields),
        "same_dataclass": same_dataclass,
        "same_schema_fields": same_schema_fields,
        "no_evidence_subclasses": no_subclasses,
        "authorization_evidence": asdict(authorization),
        "initialization_evidence": asdict(initialization),
        "arithmetic_evidence": asdict(arithmetic),
        "payload_present": payload_present,
        "payload_values_structured": payload_values_structured,
        "source_verification": arithmetic.source_verification,
        "verification_preserved": verification_preserved,
        "transport_run_marker": transport.get("run_marker"),
    }


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: python scripts/probe_evidence_schema_5b.py <project_dir> <test_path>")
    result = probe_evidence_schema(sys.argv[1], sys.argv[2])
    print(json.dumps(result, indent=2))
    if result["classification"] == "UNMEASURABLE":
        raise SystemExit(1)
