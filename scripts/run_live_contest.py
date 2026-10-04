from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import re
import traceback
import contextlib
import io
from pathlib import Path
from typing import Any, Mapping

from run_benchmark_blind import SUPPORTED_CLASSES, run_source_investigation
from cydra.capability_campaign import merge_campaigns
from cydra.capability_repair import (
    RepairRequirement,
    build_automatic_repair_plan,
    run_automatic_repair_controller,
)


REQUIRED_KEYS = {
    "program",
    "program_url",
    "target_repo",
    "target_url",
    "target_ref",
    "project_path",
    "in_scope",
    "out_of_scope",
    "rules",
}


def run(command: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)


def load_spec(path: Path) -> dict[str, Any]:
    spec = json.loads(path.read_text(encoding="utf-8"))
    missing = REQUIRED_KEYS - set(spec)
    if missing:
        raise RuntimeError(f"target spec missing keys: {sorted(missing)}")
    if not spec["in_scope"]:
        raise RuntimeError("target spec must declare at least one in-scope root")
    return spec


def verify_checkout(checkout: Path, ref: str) -> str:
    result = run(["git", "-C", str(checkout), "rev-parse", "HEAD"])
    if result.returncode != 0:
        raise RuntimeError(f"cannot read target checkout HEAD: {result.stderr.strip()}")
    head = result.stdout.strip()
    if head != ref:
        raise RuntimeError(f"target freeze mismatch: expected {ref}, got {head}")
    return head


def safe_relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def discover_sources(checkout: Path, roots: list[str]) -> list[str]:
    found: set[str] = set()
    excluded_prefixes = ("tests/", "test/", "mocks/", "mock/", "deploy/", "script/", "scripts/", "lib/", "node_modules/")
    for root_name in roots:
        root = (checkout / root_name).resolve()
        if not root.is_dir() or not root.is_relative_to(checkout.resolve()):
            raise RuntimeError(f"in-scope root is missing or escapes checkout: {root_name}")
        for source in root.rglob("*.sol"):
            relative = safe_relative(source, checkout)
            if relative.startswith(excluded_prefixes):
                continue
            text = source.read_text(encoding="utf-8", errors="ignore")
            if not re.search(r"\b(?:abstract\s+)?contract\s+[A-Za-z_][A-Za-z0-9_]*", text):
                continue
            found.add(relative)
    return sorted(found)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def prepare_shared_dependencies(checkout: Path, temp_root: Path) -> dict[str, str]:
    """Prepare dependency checkouts once for all per-source live investigations."""
    imports = "\n".join(
        source.read_text(encoding="utf-8", errors="ignore")
        for root_name in ("contracts", "circuits")
        if (checkout / root_name).is_dir()
        for source in (checkout / root_name).rglob("*.sol")
    )
    environment: dict[str, str] = {}

    if "@openzeppelin/contracts/" in imports:
        # The target's legacy security/ReentrancyGuard.sol import identifies
        # the OpenZeppelin 4.x layout. Newer OZ releases moved that file.
        oz_version = "v4.9.6" if "/security/ReentrancyGuard.sol" in imports else "v5.4.0"
        oz = temp_root / "openzeppelin-contracts"
        dependency = run([
            "git", "clone", "--depth", "1", "--branch", oz_version,
            "https://github.com/OpenZeppelin/openzeppelin-contracts.git", str(oz)
        ])
        if dependency.returncode != 0:
            raise RuntimeError(
                f"failed to prepare OpenZeppelin contracts {oz_version}: {dependency.stderr.strip()}"
            )
        environment["CYDRA_OPENZEPPELIN_CONTRACTS"] = os.fspath(oz)

    if "@openzeppelin/contracts-upgradeable/" in imports:
        oz_version = "v4.9.6" if "/security/ReentrancyGuard.sol" in imports else "v5.4.0"
        oz_upgradeable = temp_root / "openzeppelin-contracts-upgradeable"
        dependency = run([
            "git", "clone", "--depth", "1", "--branch", oz_version,
            "https://github.com/OpenZeppelin/openzeppelin-contracts-upgradeable.git",
            str(oz_upgradeable),
        ])
        if dependency.returncode != 0:
            raise RuntimeError(
                f"failed to prepare OpenZeppelin upgradeable {oz_version}: {dependency.stderr.strip()}"
            )
        environment["CYDRA_OPENZEPPELIN_UPGRADEABLE"] = os.fspath(oz_upgradeable)

    return environment


def run_automatic_repairs_for_source(
    *,
    source: str,
    result: dict[str, Any],
    spec: dict[str, Any],
    checkout: Path,
    output: Path,
    child_env: dict[str, str],
    round_number: int,
) -> dict[str, Any]:
    """Regress known generic capabilities and replay the exact frozen target."""
    classification = result.get("classification") or {}
    campaign = {
        "capability_clusters": [
            {
                "capability": key,
                "count": count,
                "hypothesis_ids": [],
                "experiment_ids": [],
                "stages": [],
                "reasons": [],
            }
            for key, count in (classification.get("capability_clusters") or {}).items()
        ]
    }
    automatic_plan = classification.get("automatic_repair")
    if automatic_plan is None:
        automatic_plan = build_automatic_repair_plan(campaign)
    if not automatic_plan.get("requirements"):
        return {"status": "no_requirements", "attempts": []}
    # Preserve the exact hypothesis/experiment provenance emitted by the
    # source-level repair contract when constructing the executable controller.
    campaign["capability_clusters"] = [
        {
            "capability": item["key"],
            "count": 1,
            "hypothesis_ids": item.get("affected_hypothesis_ids", []),
            "experiment_ids": item.get("affected_experiment_ids", []),
            "stages": [item.get("stage", "execution")],
            "reasons": [item.get("reason", "")],
        }
        for item in automatic_plan["requirements"]
    ]

    repair_root = output / "automatic-repair" / f"round-{round_number:02d}" / f"{len(source):04d}-{Path(source).stem}"
    repair_root.mkdir(parents=True, exist_ok=True)

    def regression(provider) -> bool:
        environment = os.environ.copy()
        environment.update(child_env)
        command = list(provider.regression_command)
        completed = subprocess.run(
            command,
            cwd=Path(__file__).resolve().parents[1],
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        (repair_root / "regression.stdout.txt").write_text(completed.stdout, encoding="utf-8")
        (repair_root / "regression.stderr.txt").write_text(completed.stderr, encoding="utf-8")
        write_json(repair_root / "regression.json", {
            "provider": provider.implementation_id,
            "command": command,
            "exit_code": completed.returncode,
            "passed": completed.returncode == 0,
        })
        return completed.returncode == 0

    def replay(requirement: RepairRequirement) -> Mapping[str, object]:
        replay_artifact = repair_root / "replay" / f"{requirement.key.replace(':', '__')}"
        replay_artifact.mkdir(parents=True, exist_ok=True)
        stdout = io.StringIO()
        stderr = io.StringIO()
        previous_env = os.environ.copy()
        try:
            os.environ.update(child_env)
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exit_code = run_source_investigation(
                    target_repo=checkout.as_uri(),
                    target_ref=spec["target_ref"],
                    target_path=source,
                    target_project=spec["project_path"],
                    classes=tuple(sorted(SUPPORTED_CLASSES)),
                    freeze=replay_artifact / "freeze",
                )
        finally:
            os.environ.clear()
            os.environ.update(previous_env)
        (replay_artifact / "runner.stdout.txt").write_text(stdout.getvalue(), encoding="utf-8")
        (replay_artifact / "runner.stderr.txt").write_text(stderr.getvalue(), encoding="utf-8")
        replay_campaign = {}
        classification_path = replay_artifact / "freeze" / "classification.json"
        if classification_path.is_file():
            try:
                replay_classification = json.loads(classification_path.read_text(encoding="utf-8"))
                replay_campaign = {"capability_clusters": [
                    {"capability": key, "count": count, "hypothesis_ids": [], "experiment_ids": [],
                     "stages": ["execution"], "reasons": []}
                    for key, count in (replay_classification.get("capability_clusters") or {}).items()
                ]}
            except (OSError, ValueError):
                replay_campaign = {}
        return {
            "exit_code": exit_code,
            "artifact": str(replay_artifact.relative_to(output)),
            "target_ref": spec["target_ref"],
            "hypothesis_ids": list(requirement.affected_hypothesis_ids),
            "experiment_ids": list(requirement.affected_experiment_ids),
            "campaign": replay_campaign,
        }

    return run_automatic_repair_controller(
        campaign,
        regression=regression,
        rerun_target=replay,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the single canonical CYDRA live-target dogfood pipeline.")
    parser.add_argument("--target-spec", type=Path, required=True)
    parser.add_argument("--target-checkout", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    spec = load_spec(args.target_spec)
    checkout = args.target_checkout.resolve()
    if not checkout.is_dir():
        raise RuntimeError(f"target checkout does not exist: {checkout}")

    frozen = verify_checkout(checkout, spec["target_ref"])
    sources = discover_sources(checkout, list(spec["in_scope"]))
    if not sources:
        raise RuntimeError("no Solidity sources discovered inside the declared in-scope roots")

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "target-freeze.json", {
        "program": spec["program"],
        "program_url": spec["program_url"],
        "target_repo": spec["target_repo"],
        "target_url": spec["target_url"],
        "target_ref": spec["target_ref"],
        "observed_checkout_head": frozen,
        "in_scope": spec["in_scope"],
        "out_of_scope": spec["out_of_scope"],
        "rules": spec["rules"],
        "source_count": len(sources),
        "source_selection": "concrete-or-abstract contract declarations only; interface/library/type-only Solidity files remain dependencies",
        "dependency_strategy": "import-driven shared dependency bootstrap for manifest-less public targets; dependency versions are inferred from observed import layout",
        "sources": sources,
    })

    local_repo = checkout.as_uri()
    results: list[dict[str, Any]] = []
    automatic_repairs: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="cydra-live-run-") as temp:
        temp_root = Path(temp)
        shared_forge_std = temp_root / "forge-std"
        dependency = run(["git", "clone", "--depth", "1", "https://github.com/foundry-rs/forge-std.git", str(shared_forge_std)])
        if dependency.returncode != 0:
            raise RuntimeError(f"failed to prepare shared forge-std: {dependency.stderr.strip()}")
        child_env = os.environ.copy()
        child_env["CYDRA_FORGE_STD"] = os.fspath(shared_forge_std)
        child_env.update(prepare_shared_dependencies(checkout, temp_root))
        for index, source in enumerate(sources, start=1):
            artifact = output / f"{index:04d}-{Path(source).stem}"
            artifact.mkdir(parents=True, exist_ok=True)
            stdout = io.StringIO()
            stderr = io.StringIO()
            previous_env = os.environ.copy()
            try:
                os.environ.update(child_env)
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    exit_code = run_source_investigation(
                        target_repo=local_repo,
                        target_ref=spec["target_ref"],
                        target_path=source,
                        target_project=spec["project_path"],
                        classes=tuple(sorted(SUPPORTED_CLASSES)),
                        freeze=artifact / "freeze",
                    )
            except Exception as error:
                exit_code = 1
                # Preserve the full generic pipeline traceback so a live-target
                # capability failure can be diagnosed from the artifact without
                # reproducing the target locally. The source itself remains
                # isolated; one failing source must not stop the campaign.
                stderr.write(
                    f"{type(error).__name__}: {error}\n"
                    f"{traceback.format_exc()}"
                )
            finally:
                os.environ.clear()
                os.environ.update(previous_env)
            (artifact / "runner.stdout.txt").write_text(stdout.getvalue(), encoding="utf-8")
            (artifact / "runner.stderr.txt").write_text(stderr.getvalue(), encoding="utf-8")
            result: dict[str, Any] = {
                "source": source,
                "exit_code": exit_code,
                "ok": exit_code == 0,
                "artifact": str(artifact.relative_to(output)),
            }
            classification = artifact / "freeze" / "classification.json"
            if classification.exists():
                try:
                    result["classification"] = json.loads(classification.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    result["classification_parse_error"] = True
            results.append(result)

        for result in results:
            if not result.get("ok"):
                continue
            repair = run_automatic_repairs_for_source(
                source=result["source"],
                result=result,
                spec=spec,
                checkout=checkout,
                output=output,
                child_env=child_env,
                round_number=1,
            )
            automatic_repairs.append({
                "source": result["source"],
                "repair": repair,
            })

    campaigns = []
    for result in results:
        campaign_path = output / result["artifact"] / "freeze" / "capability_failures.json"
        blocked_path = output / result["artifact"] / "freeze" / "blocked_experiments.json"
        graph_path = output / result["artifact"] / "freeze" / "dependency_graph.json"
        if campaign_path.exists():
            try:
                failures = json.loads(campaign_path.read_text(encoding="utf-8"))
                blocked = json.loads(blocked_path.read_text(encoding="utf-8")) if blocked_path.exists() else []
                graph = json.loads(graph_path.read_text(encoding="utf-8")) if graph_path.exists() else {"nodes": [], "edges": []}
                # Reconstruct the normalized campaign envelope from the immutable
                # per-source freeze files so the target-level artifact remains
                # independent of implementation details inside the runner.
                campaigns.append({
                    "summary": {
                        "total_attempts": len(failures) + len(blocked),
                        "by_status": {},
                    },
                    "capability_failures": failures,
                    "blocked_experiments": blocked,
                    "capability_clusters": [],
                    "dependency_graph": graph,
                })
            except json.JSONDecodeError:
                pass

    # Prefer classification.json for complete per-source attempt counts and
    # cluster metadata when available.
    normalized_campaigns = []
    for result in results:
        classification_path = output / result["artifact"] / "freeze" / "classification.json"
        failures_path = output / result["artifact"] / "freeze" / "capability_failures.json"
        blocked_path = output / result["artifact"] / "freeze" / "blocked_experiments.json"
        graph_path = output / result["artifact"] / "freeze" / "dependency_graph.json"
        if not (classification_path.exists() and failures_path.exists()):
            continue
        try:
            classification = json.loads(classification_path.read_text(encoding="utf-8"))
            normalized_campaigns.append({
                "source": result["source"],
                "summary": classification.get("campaign", {}),
                "capability_failures": json.loads(failures_path.read_text(encoding="utf-8")),
                "blocked_experiments": json.loads(blocked_path.read_text(encoding="utf-8")) if blocked_path.exists() else [],
                "capability_clusters": [
                    {"capability": key, "count": count, "hypothesis_ids": [], "experiment_ids": [], "stages": [], "reasons": []}
                    for key, count in (classification.get("capability_clusters") or {}).items()
                ],
                "dependency_graph": json.loads(graph_path.read_text(encoding="utf-8")) if graph_path.exists() else {"edges": []},
            })
        except json.JSONDecodeError:
            continue

    # The deterministic repair controller is part of the capability frontier.
    # Its exact-target replays are newer evidence than the source's initial
    # classification. Feed the residual replay frontier forward so the next
    # autonomous layer does not repeatedly diagnose capabilities already repaired.
    residual_campaigns: list[dict[str, Any]] = []
    repair_by_source = {item["source"]: item["repair"] for item in automatic_repairs}
    for result in results:
        source = result["source"]
        repair = repair_by_source.get(source) or {}
        attempts = repair.get("attempts") or []
        latest_replays = [
            attempt.get("replay", {}).get("campaign")
            for attempt in attempts
            if isinstance(attempt, dict)
            and isinstance(attempt.get("replay"), dict)
            and isinstance(attempt.get("replay", {}).get("campaign"), dict)
        ]
        if latest_replays:
            latest = latest_replays[-1]
            residual_campaigns.append({
                "summary": latest.get("summary", {}),
                "capability_failures": latest.get("capability_failures", []),
                "blocked_experiments": latest.get("blocked_experiments", []),
                "capability_clusters": latest.get("capability_clusters", []),
                "dependency_graph": latest.get("dependency_graph", {"edges": []}),
            })
        else:
            # No replay means no deterministic repair was applicable; preserve
            # this source's original campaign as the residual frontier.
            original = next(
                (item for item in normalized_campaigns if item.get("source") == source),
                None,
            )
            residual_campaigns.append(original or {})

    target_campaign = merge_campaigns(residual_campaigns or normalized_campaigns or campaigns)
    write_json(output / "capability_campaign.json", target_campaign)

    confirmed = []
    for result in results:
        classification = result.get("classification", {})
        for hypothesis in classification.get("hypotheses", []):
            if hypothesis.get("classification") == "confirmed":
                confirmed.append({
                    "source": result["source"],
                    "hypothesis_id": hypothesis.get("hypothesis_id"),
                    "class": hypothesis.get("class"),
                })

    write_json(output / "automatic-repair.json", {
        "schema_version": 1,
        "mode": "automatic_generic_repair",
        "target_ref": frozen,
        "repairs": automatic_repairs,
    })

    summary = {
        "status": "completed",
        "target_ref": frozen,
        "source_count": len(sources),
        "sources_completed": sum(1 for item in results if item["ok"]),
        "sources_failed": sum(1 for item in results if not item["ok"]),
        "confirmed_candidates": confirmed,
        "automatic_repairs": automatic_repairs,
        "results": results,
        "note": "A confirmed candidate still requires causal and independent human validation before submission.",
    }
    write_json(output / "summary.json", summary)
    digest = hashlib.sha256((output / "summary.json").read_bytes()).hexdigest()
    (output / "summary.sha256").write_text(f"{digest}  summary.json\n", encoding="utf-8")

    return 0 if not any(not item["ok"] for item in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
