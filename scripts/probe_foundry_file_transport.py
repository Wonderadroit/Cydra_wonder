from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any


def _foundry_version(project: Path) -> str | None:
    completed = subprocess.run(
        ["forge", "--version"],
        cwd=project,
        text=True,
        capture_output=True,
        check=False,
    )
    output = (completed.stdout or completed.stderr).strip()
    return output or None


def _shape(content: str | None) -> str:
    if content is None:
        return "not_readable"
    if not content:
        return "empty"
    try:
        json.loads(content)
    except json.JSONDecodeError:
        return "unstructured_text"
    return "structured_json"


def _permissions_declared(config: Path) -> bool:
    if not config.exists():
        return False
    text = config.read_text(encoding="utf-8")
    return bool(
        re.search(r"(?m)^\s*fs_permissions\s*=", text)
        or re.search(r"(?m)^\s*\[\[profile\.default\.fs_permissions\]\]\s*$", text)
    )


def _permissions_path(config: Path) -> str | None:
    if not config.exists():
        return None
    text = config.read_text(encoding="utf-8")
    match = re.search(
        r"(?ms)^\s*\[\[profile\.default\.fs_permissions\]\]\s*$.*?^\s*path\s*=\s*['\"]([^'\"]+)['\"]",
        text,
    )
    if match:
        return match.group(1)
    match = re.search(r"(?m)^\s*path\s*=\s*['\"]([^'\"]+)['\"]", text)
    return match.group(1) if match else None


def _runtime_payload_source_present(source: str) -> bool:
    required_runtime_expressions = (
        'vm.toString(vulnerableObserved)',
        'vm.toString(exactFloor)',
        'vm.toString(patchedObserved)',
    )
    return all(expression in source for expression in required_runtime_expressions)


def _measurement_payload_valid(payload: dict[str, Any] | None, run_marker: str) -> bool:
    if payload is None:
        return False
    required = ("observed", "referenceValue", "patched", "run_marker")
    if any(key not in payload for key in required):
        return False
    if payload.get("run_marker") != run_marker:
        return False
    return all(isinstance(payload[key], int) and not isinstance(payload[key], bool) for key in required[:3])


def probe_file_transport(project_dir: str | Path, test_path: str | Path) -> dict[str, Any]:
    project = Path(project_dir).resolve()
    test = Path(test_path).resolve()
    config = project / "foundry.toml"
    probe_relative = Path("cydra_file_transport_probe.json")
    probe_path = project / probe_relative
    original = test.read_text(encoding="utf-8")
    run_marker = uuid.uuid4().hex

    # Remove any previous artifact before execution so a stale file cannot satisfy the probe.
    if probe_path.exists():
        probe_path.unlink()

    marker = "assertGt(vulnerableObserved, exactFloor);"
    if marker not in original:
        raise RuntimeError("existing arithmetic test does not contain the expected assertion marker")

    # The payload is assembled inside executed Solidity from runtime values already
    # produced by the vulnerable/patched calls and the Solidity reference calculation.
    # Python only reads the resulting JSON; it does not calculate these values.
    write_call = (
        'vm.writeFile("cydra_file_transport_probe.json", '
        f"string.concat('{{\\\"observed\\\":', vm.toString(vulnerableObserved), "
        "',\\\"referenceValue\\\":', vm.toString(exactFloor), "
        "',\\\"patched\\\":', vm.toString(patchedObserved), "
        f"',\\\"run_marker\\\":\\\"{run_marker}\\\"}}')"
        ");"
    )
    modified = original.replace(marker, write_call + "\n        " + marker, 1)
    test.write_text(modified, encoding="utf-8")

    try:
        completed = subprocess.run(
            ["forge", "test", "--match-path", str(test.relative_to(project))],
            cwd=project,
            text=True,
            capture_output=True,
            check=False,
        )

        file_content: str | None = None
        if probe_path.exists():
            file_content = probe_path.read_text(encoding="utf-8")

        parsed_content: dict[str, Any] | None = None
        if file_content:
            try:
                candidate = json.loads(file_content)
                if isinstance(candidate, dict):
                    parsed_content = candidate
            except json.JSONDecodeError:
                pass

        fresh_write_confirmed = bool(
            parsed_content is not None and parsed_content.get("run_marker") == run_marker
        )
        payload_valid = _measurement_payload_valid(parsed_content, run_marker)
        runtime_payload_source_present = _runtime_payload_source_present(modified)

        error_output = f"{completed.stdout}\n{completed.stderr}".strip()
        fs_permission_error = bool(
            re.search(r"fs_permissions|permission denied|access denied|not allowed", error_output, re.IGNORECASE)
        )
        ffi_required = "ffi" in error_output.lower() and "--ffi" in error_output.lower()

        if completed.returncode == 0:
            classification = (
                "CONFIRMED"
                if fresh_write_confirmed
                and _shape(file_content) == "structured_json"
                and payload_valid
                and runtime_payload_source_present
                else "FALSIFIED"
            )
        elif fs_permission_error:
            classification = "FALSIFIED"
        else:
            classification = "UNMEASURABLE"

        result = {
            "cheat_code_used": "vm.writeFile",
            "invoked_successfully": completed.returncode == 0,
            "error_if_failed": None if completed.returncode == 0 else error_output[-4000:],
            "fs_permissions_required": fs_permission_error,
            "fs_permissions_declared": _permissions_declared(config),
            "fs_permissions_path": _permissions_path(config),
            "ffi_required": ffi_required,
            "ffi_enabled": False,
            "file_written": fresh_write_confirmed,
            "file_path": str(probe_relative),
            "file_content_readable_by_python": file_content is not None and fresh_write_confirmed,
            "file_content_shape": _shape(file_content) if fresh_write_confirmed else "not_readable",
            "fresh_write_confirmed": fresh_write_confirmed,
            "measurement_payload_present": payload_valid,
            "runtime_measurement_source_present": runtime_payload_source_present,
            "measurement_payload": parsed_content if payload_valid else None,
            "run_marker": run_marker,
            "classification": classification,
            "environment": {
                "foundry_version": _foundry_version(project),
                "ci_runner": "github-actions" if os.environ.get("GITHUB_ACTIONS") == "true" else "local",
                "test_config": str(config.relative_to(project)),
            },
        }
    finally:
        test.write_text(original, encoding="utf-8")
        if probe_path.exists():
            probe_path.unlink()

    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir")
    parser.add_argument("test_path")
    args = parser.parse_args()
    result = probe_file_transport(args.project_dir, args.test_path)
    print(json.dumps(result, indent=2))
    if result["classification"] == "UNMEASURABLE":
        sys.exit(1)
