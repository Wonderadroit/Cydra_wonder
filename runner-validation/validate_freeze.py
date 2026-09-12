#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


FREEZE_FILES = (
    "provenance.json",
    "target-checkout.txt",
    "parse-output.json",
    "invariants.json",
    "hypotheses.json",
    "experiments.json",
    "compilation.log",
    "execution.json",
    "execution-human.txt",
    "integrity-check.json",
    "classification.json",
    "manifest.sha256",
    "README.md",
)

EXECUTION_STATUS_FIELD = "execution_result.status"


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid JSON: {path}: {exc}") from exc


def expected_record(expected: dict[str, Any]) -> dict[str, Any]:
    record = expected.get("expected")
    if not isinstance(record, dict):
        raise RuntimeError("expected.json must contain an 'expected' object")
    return record


def actual_hypotheses(
    classification: dict[str, Any],
) -> list[dict[str, Any]]:
    hypotheses = classification.get("hypotheses")
    if not isinstance(hypotheses, list):
        raise RuntimeError(
            "freeze/classification.json must contain a 'hypotheses' array"
        )
    return hypotheses


def compare_value(
    layers: dict[str, Any],
    failures: list[str],
    field: str,
    expected: Any,
    actual: Any,
) -> None:
    match = expected == actual

    layers[field] = {
        "expected": expected,
        "actual": actual,
        "match": match,
    }

    if not match:
        failures.append(
            f"{field}: expected {expected!r}, actual {actual!r}"
        )


def validate_manifest(
    freeze: Path,
    failures: list[str],
) -> str:
    manifest_path = freeze / "manifest.sha256"

    if not manifest_path.exists():
        failures.append("manifest.sha256: missing")
        return ""

    lines = [
        line.strip()
        for line in manifest_path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]

    expected_manifest: dict[str, str] = {}

    for line in lines:
        try:
            digest, name = line.split("  ", 1)
        except ValueError:
            failures.append(
                f"manifest.sha256: malformed line: {line!r}"
            )
            continue

        expected_manifest[name] = digest

    for name in FREEZE_FILES:
        if name == "manifest.sha256":
            continue

        path = freeze / name

        if not path.exists():
            failures.append(
                f"manifest: missing freeze file {name}"
            )
            continue

        actual_digest = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()

        expected_digest = expected_manifest.get(name)

        if expected_digest is None:
            failures.append(
                f"manifest: no digest recorded for {name}"
            )
        elif actual_digest != expected_digest:
            failures.append(
                f"manifest: digest mismatch for {name}: "
                f"expected {expected_digest}, "
                f"actual {actual_digest}"
            )

    return hashlib.sha256(
        manifest_path.read_bytes()
    ).hexdigest()


def execution_result_for(
    hypothesis: dict[str, Any],
    execution: dict[str, Any],
) -> dict[str, Any] | None:
    embedded = hypothesis.get("execution_result")

    if isinstance(embedded, dict):
        return embedded

    hypothesis_id = hypothesis.get("hypothesis_id")
    records = execution.get("results")

    if isinstance(records, list):
        for record in records:
            if record.get("hypothesis_id") == hypothesis_id:
                return record

    return None


def validate_check(
    check_dir: Path,
) -> dict[str, Any]:
    expected_path = check_dir / "expected.json"
    freeze = check_dir / "freeze"

    expected_doc = load_json(expected_path)
    expected = expected_record(expected_doc)

    failures: list[str] = []

    if not freeze.is_dir():
        failures.append("freeze: directory missing")

        return {
            "check_name": expected_doc.get(
                "name",
                check_dir.name,
            ),
            "overall": "FAIL",
            "layers": {},
            "failures": failures,
        }

    manifest_sha256 = validate_manifest(
        freeze,
        failures,
    )

    classification = load_json(
        freeze / "classification.json"
    )

    execution = load_json(
        freeze / "execution.json"
    )

    hypotheses = actual_hypotheses(
        classification
    )

    if not hypotheses:
        failures.append(
            "classification.hypotheses: empty"
        )

    applicable = hypotheses

    layers: dict[str, Any] = {}

    # IMPORTANT:
    # has_patched_target is intentionally excluded.
    #
    # It is invocation/context metadata, not a frozen
    # runner result.
    expected_fields = {
        key: value
        for key, value in expected.items()
        if key != "has_patched_target"
    }

    for field in (
        "extraction",
        "hypothesis_generated",
        "experiment_planned",
        "foundry_generated",
        "blind_executed",
    ):
        if field not in expected_fields:
            continue

        expected_value = expected_fields[field]

        actual_values = [
            record.get("extracted")
            if field == "extraction"
            else record.get(field)
            for record in applicable
        ]

        # Convert the collection of applicable hypothesis records
        # into the actual boolean state for this layer.
        #
        # True is reported only when every applicable record is True.
        # False is therefore preserved when the applicable records
        # correctly report a blocked/unsupported capability.
        actual = all(
            value is True
            for value in actual_values
        )

        compare_value(
            layers,
            failures,
            field,
            expected_value,
            actual,
        )

    if "classification" in expected_fields:
        expected_classification = (
            expected_fields["classification"]
        )

        allowed = {
            value.strip()
            for value in str(
                expected_classification
            ).split("|")
            if value.strip()
        }

        actual_values = [
            record.get("classification")
            for record in applicable
        ]

        classification_ok = all(
            value in allowed
            for value in actual_values
        )

        layers["classification"] = {
            "expected": expected_classification,
            "actual": actual_values,
            "match": classification_ok,
        }

        if not classification_ok:
            failures.append(
                "classification: actual value outside "
                f"expected set: expected "
                f"{sorted(allowed)}, "
                f"actual {actual_values}"
            )

    for field in (
        "generation_attempted",
        "execution_attempted",
        "foundry_generation_blocked_reason",
        "classification_blocked_reason",
    ):
        if field not in expected_fields:
            continue

        expected_value = expected_fields[field]

        for index, record in enumerate(applicable):
            actual = record.get(field)

            key = f"{field}[{index}]"

            compare_value(
                layers,
                failures,
                key,
                expected_value,
                actual,
            )

    expected_status = None

    if "execution_status" in expected_fields:
        expected_status = expected_fields[
            "execution_status"
        ]

    elif "execution_result" in expected_fields:
        expected_execution = (
            expected_fields["execution_result"]
        )

        if not isinstance(
            expected_execution,
            dict,
        ):
            raise RuntimeError(
                "expected.execution_result must be an object"
            )

        expected_status = expected_execution.get(
            "status"
        )

    if expected_status is not None:
        actual_execution_records = []

        for record in applicable:
            result = execution_result_for(
                record,
                execution,
            )

            actual_execution_records.append(
                result
            )

        actual_statuses = [
            result.get("status")
            if result
            else None
            for result in actual_execution_records
        ]

        status_ok = all(
            status == expected_status
            for status in actual_statuses
        )

        layers[EXECUTION_STATUS_FIELD] = {
            "expected": expected_status,
            "actual": actual_statuses,
            "match": status_ok,
        }

        if not status_ok:
            failures.append(
                "execution_result.status: "
                f"expected {expected_status!r}, "
                f"actual {actual_statuses!r}"
            )

    provenance = load_json(
        freeze / "provenance.json"
    )

    runner_commit = provenance.get(
        "runner_commit"
    )

    return {
        "check_name": expected_doc.get(
            "name",
            check_dir.name,
        ),
        "freeze_manifest_sha256": manifest_sha256,
        "runner_commit": runner_commit,
        "overall": (
            "PASS"
            if not failures
            else "FAIL"
        ),
        "layers": layers,
        "failures": failures,
    }


def validate_config(
    config_path: Path,
) -> list[str]:
    """
    Pre-flight configuration sanity check.

    This is deliberately NOT part of freeze validation.

    It checks only that patched_path and
    patched_contract are either both present
    or both absent.

    It does not inject has_patched_target into
    validation.json.
    """

    config = load_json(config_path)

    failures: list[str] = []

    patched_path = config.get(
        "patched_path"
    )

    patched_contract = config.get(
        "patched_contract"
    )

    path_present = patched_path not in (
        None,
        "",
    )

    contract_present = patched_contract not in (
        None,
        "",
    )

    if path_present != contract_present:
        failures.append(
            "config: patched_path and "
            "patched_contract must either both "
            "be present or both be absent"
        )

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate frozen CYDRA benchmark "
            "runner outputs."
        )
    )

    parser.add_argument(
        "checks",
        nargs="*",
        type=Path,
        help=(
            "check directories; defaults to "
            "all check-* directories"
        ),
    )

    args = parser.parse_args()

    root = Path(__file__).resolve().parent

    checks = args.checks

    if not checks:
        checks = sorted(
            path
            for path in root.iterdir()
            if path.is_dir()
            and path.name.startswith("check-")
        )

    if not checks:
        print(
            "No runner-validation check directories found.",
            file=sys.stderr,
        )
        return 2

    results = []

    preflight_failures: dict[
        str,
        list[str],
    ] = {}

    for check in checks:
        check = check.resolve()

        config_path = check / "config.json"
        expected_path = check / "expected.json"

        if not config_path.exists():
            preflight_failures[
                check.name
            ] = [
                "config.json: missing"
            ]

        if not expected_path.exists():
            preflight_failures.setdefault(
                check.name,
                [],
            ).append(
                "expected.json: missing"
            )
            continue

        try:
            config_failures = validate_config(
                config_path
            )

            if config_failures:
                preflight_failures[
                    check.name
                ] = config_failures

            result = validate_check(
                check
            )

        except Exception as exc:
            result = {
                "check_name": check.name,
                "overall": "FAIL",
                "layers": {},
                "failures": [
                    "validator error: "
                    f"{type(exc).__name__}: {exc}"
                ],
            }

        results.append(result)

    output = {
        "validator": (
            "runner-validation/"
            "validate_freeze.py"
        ),
        "contract": (
            "freeze/ + expected.json "
            "-> validation.json"
        ),
        "has_patched_target": (
            "excluded_from_validation_surface"
        ),
        "preflight_config_failures": (
            preflight_failures
        ),
        "checks": results,
        "overall": (
            "PASS"
            if (
                results
                and all(
                    result["overall"] == "PASS"
                    for result in results
                )
                and not preflight_failures
            )
            else "FAIL"
        ),
    }

    output_path = (
        root / "validation.json"
    )

    output_path.write_text(
        json.dumps(
            output,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            output,
            indent=2,
            sort_keys=True,
        )
    )

    return (
        0
        if output["overall"] == "PASS"
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
