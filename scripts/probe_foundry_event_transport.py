from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


VARIANTS = {
    "json": ("--json",),
    "vv": ("-vv",),
    "vvv": ("-vvv",),
    "vvvv": ("-vvvv",),
}


def _contains_event(value: Any) -> bool:
    if isinstance(value, str):
        return "CydraMeasurement" in value
    if isinstance(value, dict):
        return any(_contains_event(key) or _contains_event(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_event(item) for item in value)
    return False


def probe_event_transport(project_dir: str | Path, test_path: str | Path) -> dict[str, object]:
    project = Path(project_dir)
    relative_test = Path(test_path)
    if relative_test.is_absolute():
        relative_test = relative_test.relative_to(project)

    results: dict[str, object] = {}
    for name, flags in VARIANTS.items():
        command = ["forge", "test", "--match-path", str(relative_test), *flags]
        completed = subprocess.run(
            command,
            cwd=project,
            text=True,
            capture_output=True,
            check=False,
        )
        stdout = completed.stdout
        stderr = completed.stderr
        parsed_json = None
        json_structured_event = False
        if name == "json":
            try:
                parsed_json = json.loads(stdout)
                json_structured_event = _contains_event(parsed_json)
            except json.JSONDecodeError:
                parsed_json = None

        results[name] = {
            "command": command,
            "exit_code": completed.returncode,
            "event_visible_in_output": "CydraMeasurement" in f"{stdout}\n{stderr}",
            "structured_json": name == "json" and parsed_json is not None,
            "structured_event": json_structured_event,
        }

    json_result = results["json"]
    structured_json_event = bool(json_result["structured_event"]) if isinstance(json_result, dict) else False
    human_event_variants = [
        name
        for name in ("vv", "vvv", "vvvv")
        if isinstance(results[name], dict) and results[name]["event_visible_in_output"]
    ]

    if structured_json_event:
        classification = "STRUCTURED_JSON"
    elif human_event_variants:
        classification = "HUMAN_READABLE_ONLY"
    else:
        classification = "NOT_EXPOSED"

    return {
        "probe": "Prediction 5A-Probe",
        "classification": classification,
        "structured_json_event": structured_json_event,
        "human_readable_event_variants": human_event_variants,
        "variants": results,
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir")
    parser.add_argument("test_path")
    args = parser.parse_args()
    result = probe_event_transport(args.project_dir, args.test_path)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
