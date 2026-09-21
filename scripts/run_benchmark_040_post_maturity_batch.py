from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", type=Path, default=Path("benchmarks/040_post_maturity_batch/targets.json"))
    p.add_argument("--output", type=Path, default=Path("backtest-artifacts/benchmark-040"))
    args = p.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    args.output.mkdir(parents=True, exist_ok=True)
    campaign = {
        "campaign": manifest["campaign"],
        "name": manifest["name"],
        "baseline_commit": manifest["baseline_commit"],
        "blind_policy": manifest["blind_policy"],
        "classes": manifest["classes"],
        "targets": [],
    }

    for target in manifest["targets"]:
        started = time.monotonic()
        target_dir = args.output / target["id"]
        target_dir.mkdir(parents=True, exist_ok=True)
        freeze = target_dir / "freeze"
        command = [
            sys.executable,
            "scripts/run_benchmark_blind.py",
            "--target-repo", target["repo"],
            "--target-ref", target["ref"],
            "--target-path", target["path"],
            "--target-project", target["project"],
            "--classes", *manifest["classes"],
            "--freeze", str(freeze),
        ]
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
        elapsed = time.monotonic() - started
        record = {
            "target": target,
            "command": command,
            "exit_code": completed.returncode,
            "elapsed_seconds": round(elapsed, 3),
            "stdout_tail": completed.stdout[-12000:],
            "stderr_tail": completed.stderr[-12000:],
            "artifact_exists": freeze.exists(),
        }
        if freeze.exists() and (freeze / "classification.json").exists():
            record["classification"] = json.loads((freeze / "classification.json").read_text(encoding="utf-8"))
        if freeze.exists() and (freeze / "hypotheses.json").exists():
            hypotheses = json.loads((freeze / "hypotheses.json").read_text(encoding="utf-8"))
            record["hypothesis_count"] = len(hypotheses)
        if freeze.exists() and (freeze / "experiments.json").exists():
            experiments = json.loads((freeze / "experiments.json").read_text(encoding="utf-8"))
            record["experiment_count"] = len(experiments)
        (target_dir / "campaign-record.json").write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        campaign["targets"].append(record)

    successful_artifacts = sum(1 for x in campaign["targets"] if x["artifact_exists"])
    campaign["summary"] = {
        "targets_total": len(campaign["targets"]),
        "artifacts_produced": successful_artifacts,
        "artifacts_missing": len(campaign["targets"]) - successful_artifacts,
        "total_elapsed_seconds": round(sum(x["elapsed_seconds"] for x in campaign["targets"]), 3),
        "blind_boundary_preserved": all(
            value is False for value in manifest["blind_policy"].values()
        ),
    }
    (args.output / "campaign.json").write_text(
        json.dumps(campaign, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(campaign["summary"], indent=2, sort_keys=True))
    return 0 if successful_artifacts == len(campaign["targets"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
