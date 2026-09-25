from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import re
from pathlib import Path
from typing import Any


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the canonical CYDRA research pipeline against one pinned live contest target.")
    parser.add_argument("--target-spec", type=Path, required=True)
    parser.add_argument("--target-checkout", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--classes", nargs="+", default=["authorization", "initialization", "arithmetic", "state", "guard_parity"])
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
        "sources": sources,
    })

    local_repo = checkout.as_uri()
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="cydra-live-run-") as temp:
        temp_root = Path(temp)
        shared_forge_std = temp_root / "forge-std"
        dependency = run(["git", "clone", "--depth", "1", "https://github.com/foundry-rs/forge-std.git", str(shared_forge_std)])
        if dependency.returncode != 0:
            raise RuntimeError(f"failed to prepare shared forge-std: {dependency.stderr.strip()}")
        child_env = os.environ.copy()
        child_env["CYDRA_FORGE_STD"] = os.fspath(shared_forge_std)
        for index, source in enumerate(sources, start=1):
            artifact = output / f"{index:04d}-{Path(source).stem}"
            artifact.mkdir(parents=True, exist_ok=True)
            command = [
                os.fspath(Path(__file__).resolve().parent / "run_benchmark_blind.py"),
                "--target-repo", local_repo,
                "--target-ref", spec["target_ref"],
                "--target-path", source,
                "--target-project", spec["project_path"],
                "--classes", *args.classes,
                "--freeze", str(artifact / "freeze"),
            ]
            completed = subprocess.run(["python", *command], text=True, capture_output=True, check=False, env=child_env)
            (artifact / "runner.stdout.txt").write_text(completed.stdout, encoding="utf-8")
            (artifact / "runner.stderr.txt").write_text(completed.stderr, encoding="utf-8")
            result: dict[str, Any] = {
                "source": source,
                "exit_code": completed.returncode,
                "ok": completed.returncode == 0,
                "artifact": str(artifact.relative_to(output)),
            }
            classification = artifact / "freeze" / "classification.json"
            if classification.exists():
                try:
                    result["classification"] = json.loads(classification.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    result["classification_parse_error"] = True
            results.append(result)

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

    summary = {
        "status": "completed",
        "target_ref": frozen,
        "source_count": len(sources),
        "sources_completed": sum(1 for item in results if item["ok"]),
        "sources_failed": sum(1 for item in results if not item["ok"]),
        "confirmed_candidates": confirmed,
        "results": results,
        "note": "A confirmed candidate still requires causal and independent human validation before submission.",
    }
    write_json(output / "summary.json", summary)
    digest = hashlib.sha256((output / "summary.json").read_bytes()).hexdigest()
    (output / "summary.sha256").write_text(f"{digest}  summary.json\n", encoding="utf-8")

    return 0 if not any(not item["ok"] for item in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
