"""Run the post-maturity discovery campaigns as one auditable batch.

This deliberately composes existing benchmark runners rather than adding a new
detector or changing their semantics.
"""
from __future__ import annotations

import json
import concurrent.futures
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
    def run_case(case: tuple[str, str]) -> dict:
        name, runner = case
        started = time.monotonic()
        completed = subprocess.run(
            [sys.executable, runner],
            text=True,
            capture_output=True,
            check=False,
        )
        return {
            "name": name,
            "runner": runner,
            "exit_code": completed.returncode,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "stdout_tail": completed.stdout[-12000:],
            "stderr_tail": completed.stderr[-12000:],
        }

    # These campaigns are independent. Run them concurrently so a slow
    # unfamiliar-target batch cannot prevent causal and negative-control
    # evidence from being collected.
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(CASES)) as pool:
        records = list(pool.map(run_case, CASES))

    records.sort(key=lambda item: item["name"])
    for record in records:
        (root / (record["name"] + ".json")).write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

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
