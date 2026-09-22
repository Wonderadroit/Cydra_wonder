"""Run the post-maturity discovery campaigns as one auditable batch.

This deliberately composes existing benchmark runners rather than adding a new
detector or changing their semantics.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

CASES = (
    ("040-unfamiliar-target-batch", "scripts/run_benchmark_040_post_maturity_batch.py"),
    ("043-multi-target-causal-discovery", "scripts/run_benchmark_043_multi_target_causal_discovery.py"),
    ("044-negative-controls", "scripts/run_benchmark_044_post_maturity_negative_controls.py"),
)


def main() -> int:
    root = Path("backtest-artifacts/benchmark-050")
    root.mkdir(parents=True, exist_ok=True)
    records = []
    for name, runner in CASES:
        started = time.monotonic()
        completed = subprocess.run(
            [sys.executable, runner],
            text=True,
            capture_output=True,
            check=False,
        )
        elapsed = time.monotonic() - started
        record = {
            "name": name,
            "runner": runner,
            "exit_code": completed.returncode,
            "elapsed_seconds": round(elapsed, 3),
            "stdout_tail": completed.stdout[-12000:],
            "stderr_tail": completed.stderr[-12000:],
        }
        records.append(record)
        (root / f"{name}.json").write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if completed.returncode != 0:
            # Preserve the first failed campaign's evidence and stop rather
            # than allowing a later green campaign to hide a blocker.
            break

    passed = len(records) == len(CASES) and all(x["exit_code"] == 0 for x in records)
    result = {
        "campaign": "050-post-maturity-discovery-batch",
        "status": "PASS" if passed else "BLOCKED",
        "campaigns_total": len(CASES),
        "campaigns_completed": len(records),
        "campaigns_passed": sum(x["exit_code"] == 0 for x in records),
        "fail_closed_on_first_blocker": True,
        "results": records,
    }
    (root / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
