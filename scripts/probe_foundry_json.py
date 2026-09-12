#!/usr/bin/env python3
"""Diagnostic probe for Foundry --json output; produces no benchmark result."""
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

    command = [
        "forge",
        "test",
        "--json",
        "--match-path",
        "test/cydra_generated/*.t.sol",
    ]
    result = subprocess.run(command, cwd=root, text=True, capture_output=True)
    raw = result.stdout
    print("PROBE: command =", " ".join(command))
    print("PROBE: raw_json_size_bytes =", len(raw.encode("utf-8")))
    print("PROBE: exit_code =", result.returncode)
    print("PROBE: stderr =", result.stderr.strip())

    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        print("PROBE: json_parse = FAIL")
        print("PROBE: json_error =", exc)
        print("PROBE: raw_prefix =", repr(raw[:4000]))
        return 0

    print("PROBE: json_parse = PASS")
    if isinstance(document, dict):
        print("PROBE: top_level_keys =", sorted(document.keys()))
    else:
        print("PROBE: top_level_type =", type(document).__name__)

    def show(label: str, value: object) -> None:
        print(f"PROBE: {label} =")
        print(json.dumps(value, indent=2, sort_keys=True)[:12000])

    if isinstance(document, dict):
        for key, value in document.items():
            if isinstance(value, dict):
                entries = list(value.items())
                if entries:
                    show(f"map_entry_structure[{key}]", entries[0])
                    break
            if isinstance(value, list) and value:
                show(f"list_entry_structure[{key}]", value[0])
                break

        for key in ("summary", "results", "suites", "tests"):
            if key in document:
                show(f"summary_or_results[{key}]", document[key])

    print("PROBE: raw_json_prefix =", repr(raw[:4000]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
