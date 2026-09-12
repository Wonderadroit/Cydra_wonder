#!/usr/bin/env python3
"""Diagnostic probe for Foundry --json and human-readable output; produces no benchmark result."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from cydra.foundry import generate_initialization_test
from cydra.models import Hypothesis
from cydra.solidity_model import parse_solidity


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("liquidclaw")
    output = root / "test" / "cydra_generated"
    output.mkdir(parents=True, exist_ok=True)
    targets = (
        ("Pool", "contracts/Pool.sol", "../contracts/Pool.sol"),
        ("Minter", "contracts/Minter.sol", "../contracts/Minter.sol"),
        ("Voter", "contracts/Voter.sol", "../contracts/Voter.sol"),
    )

    for name, source_path, import_path in targets:
        source = root / source_path
        model = next(c for c in parse_solidity(source) if c.name == name)
        hypothesis = Hypothesis(
            hypothesis_id=f"H-INIT-{name}",
            claim="interface-aware initialization generation",
            invariant_id="INV-INIT-001",
            target_function="initialize",
            attacker_capability="external caller",
            expected_impact="initialization",
        )
        generate_initialization_test(
            hypothesis,
            import_path,
            name,
            output / f"{name}.t.sol",
            contract_model=model,
        )

    version = subprocess.run(["forge", "--version"], text=True, capture_output=True)
    print("PROBE: forge --version exit_code =", version.returncode)
    print("PROBE: forge --version stdout =", version.stdout.strip())
    print("PROBE: forge --version stderr =", version.stderr.strip())

    json_command = [
        "forge",
        "test",
        "--json",
        "--match-path",
        "test/cydra_generated/*.t.sol",
    ]
    json_result = subprocess.run(json_command, cwd=root, text=True, capture_output=True)
    raw = json_result.stdout
    print("PROBE: json_command =", " ".join(json_command))
    print("PROBE: raw_json_size_bytes =", len(raw.encode("utf-8")))
    print("PROBE: json_exit_code =", json_result.returncode)
    print("PROBE: json_stderr =", json_result.stderr.strip())

    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        print("PROBE: json_parse = FAIL")
        print("PROBE: json_error =", exc)
        print("PROBE: raw_prefix =", repr(raw[:4000]))
        document = None

    if isinstance(document, dict):
        print("PROBE: json_parse = PASS")
        print("PROBE: top_level_keys =", sorted(document.keys()))

        suite_path, suite = next(iter(document.items()))
        print("PROBE: first_suite_path =", suite_path)
        print("PROBE: first_suite_keys =", sorted(suite.keys()))

        test_results = suite.get("test_results")
        if isinstance(test_results, dict) and test_results:
            test_name, test_result = next(iter(test_results.items()))
            print("PROBE: first_test_name =", test_name)
            print("PROBE: first_test_entry_keys =", sorted(test_result.keys()))
            print("PROBE: first_test_entry =")
            print(json.dumps(test_result, indent=2, sort_keys=True)[:12000])
        else:
            print("PROBE: per_test_results = ABSENT")

        summary_candidates = {
            key: document[key]
            for key in ("summary", "results", "suites", "tests")
            if key in document
        }
        if summary_candidates:
            print("PROBE: summary_block =")
            print(json.dumps(summary_candidates, indent=2, sort_keys=True)[:12000])
        else:
            print("PROBE: summary_block = ABSENT")

        print("PROBE: raw_json_prefix =", repr(raw[:4000]))
    elif document is not None:
        print("PROBE: json_parse = PASS")
        print("PROBE: top_level_type =", type(document).__name__)
        print("PROBE: required_structure = INSUFFICIENT")

    human_command = [
        "forge",
        "test",
        "--match-path",
        "test/cydra_generated/*.t.sol",
    ]
    human_result = subprocess.run(human_command, cwd=root, text=True, capture_output=True)
    human_output = human_result.stdout
    print("PROBE: human_command =", " ".join(human_command))
    print("PROBE: human_exit_code =", human_result.returncode)
    print("PROBE: human_stderr =", human_result.stderr.strip())
    print("PROBE: human_output_size_bytes =", len(human_output.encode("utf-8")))
    print("PROBE: human_output_begin")
    print(human_output, end="" if human_output.endswith("\n") else "\n")
    print("PROBE: human_output_end")

    suite_lines = [
        line for line in human_output.splitlines()
        if "Suite result:" in line
    ]
    aggregate_lines = [
        line for line in human_output.splitlines()
        if line.startswith("Ran ")
    ]
    print("PROBE: suite_result_lines =")
    for line in suite_lines:
        print(line)
    if not suite_lines:
        print("PROBE: suite_result_lines = ABSENT")
    print("PROBE: aggregate_lines =")
    for line in aggregate_lines:
        print(line)
    if not aggregate_lines:
        print("PROBE: aggregate_lines = ABSENT")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
