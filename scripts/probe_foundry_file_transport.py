from __future__ import annotations

import json
import re
import subprocess
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
    return bool(re.search(r"(?m)^\s*fs_permissions\s*=", text))


def probe_file_transport(project_dir: str | Path, test_path: str | Path) -> dict[str, Any]:
    project = Path(project_dir).resolve()
    test = Path(test_path).resolve()
    config = project / "foundry.toml"
    probe_relative = Path("cydra_file_transport_probe.json")
    probe_path = project / probe_relative
    original = test.read_text(encoding="utf-8")

    marker = "assertGt(vulnerableObserved, exactFloor);"
    if marker not in original:
        raise RuntimeError("existing arithmetic test does not contain the expected assertion marker")

    write_call = (
        'vm.writeFile("cydra_file_transport_probe.json", '
        '\'{"transport":"file","probe":"executed-solidity"}\');'
    )
    modified = original.replace(marker, write_call + "\n        " + marker, 1)
    test.write_text(modified, encoding="utf-8")

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

    error_output = f"{completed.stdout}\n{completed.stderr}".strip()
    fs_permission_error = bool(
        re.search(r"fs_permissions|permission denied|access denied|not allowed", error_output, re.IGNORECASE)
    )
    ffi_required = "ffi" in error_output.lower() and "--ffi" in error_output.lower()

    result = {
        "cheat_code_used": "vm.writeFile",
        "invoked_successfully": completed.returncode == 0,
        "error_if_failed": None if completed.returncode == 0 else error_output[-4000:],
        "fs_permissions_required": fs_permission_error,
        "fs_permissions_declared": _permissions_declared(config),
        "ffi_required": ffi_required,
        "ffi_enabled": False,
        "file_written": probe_path.exists(),
        "file_path": str(probe_relative),
        "file_content_readable_by_python": file_content is not None,
        "file_content_shape": _shape(file_content),
        "environment": {
            "foundry_version": _foundry_version(project),
            "ci_runner": "github-actions" if __import__("os").environ.get("GITHUB_ACTIONS") == "true" else "local",
            "test_config": str(config.relative_to(project)),
        },
    }

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
    print(json.dumps(probe_file_transport(args.project_dir, args.test_path), indent=2))
