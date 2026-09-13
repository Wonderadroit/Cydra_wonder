from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cydra.foundry import ExecutionResult, generate_initialization_test, require_executed, run_foundry_test, test_path_for
from cydra.initialization_runtime import classify_initialization_execution
from cydra.initialization_topology import adapt_generated_initialization_for_proxy, requires_proxy_initialization
from cydra.pipeline import investigate

SUPPORTED_CLASSES = {"authorization", "initialization", "arithmetic"}
INVARIANT_CLASS = {"INV-AUTH-001": "authorization", "INV-INIT-001": "initialization", "INV-ARITH-001": "arithmetic"}
FREEZE_FILES = ("provenance.json", "target-checkout.txt", "parse-output.json", "invariants.json", "hypotheses.json", "experiments.json", "execution.json", "execution-human.txt", "integrity-check.json", "classification.json", "manifest.sha256", "README.md")
GENERATED_MANIFEST = "manifest.sha256"


def _json(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return {k: _json(v) for k, v in asdict(value).items()}
    if isinstance(value, Path): return str(value)
    if isinstance(value, tuple): return [_json(v) for v in value]
    if isinstance(value, list): return [_json(v) for v in value]
    if isinstance(value, dict): return {str(k): _json(v) for k, v in value.items()}
    return value


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(_json(value), indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(("git", *args), cwd=cwd, text=True, capture_output=True, check=True).stdout.strip()


def capture(cwd: Path, *args: str) -> dict[str, Any]:
    p = subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=False)
    return {"command": list(args), "exit_code": p.returncode, "stdout": p.stdout, "stderr": p.stderr, "ok": p.returncode == 0}


def clone_target(repo: str, ref: str, destination: Path) -> None:
    subprocess.run(("git", "clone", "--no-tags", repo, str(destination)), check=True)
    subprocess.run(("git", "-C", str(destination), "checkout", "--detach", ref), check=True)


def contract_for(result, hypothesis):
    for contract in result.contracts:
        if any(fn.name == hypothesis.target_function for fn in contract.functions): return contract
    raise RuntimeError(f"no contract model contains {hypothesis.target_function}")


def target_import(contract, project: Path) -> str:
    return os.path.relpath(Path(contract.source), project).replace(os.sep, "/")


def run_initialization(project: Path, hypothesis, experiment, contract):
    output = test_path_for(project, f"generated/{hypothesis.hypothesis_id}.t.sol")
    generated = generate_initialization_test(hypothesis, target_import(contract, project), contract.name, output, contract_model=contract)
    if requires_proxy_initialization(Path(contract.source)):
        generated.write_text(adapt_generated_initialization_for_proxy(generated.read_text(encoding="utf-8"), contract.name), encoding="utf-8")
    execution = run_foundry_test(project, generated, experiment.experiment_id, "blind")
    require_executed(execution)
    outcome = classify_initialization_execution(hypothesis, execution)
    return generated, execution, outcome


def manifest(freeze: Path):
    return [f"{hashlib.sha256((freeze / name).read_bytes()).hexdigest()}  {name}" for name in FREEZE_FILES if name != GENERATED_MANIFEST]


def freeze(files: dict[str, Any], texts: dict[str, str], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cydra-b005-", dir=destination.parent) as tmp:
        root = Path(tmp) / destination.name
        root.mkdir()
        for name, value in files.items(): write_json(root / name, value)
        for name, text in texts.items(): (root / name).write_text(text, encoding="utf-8")
        required_inputs = [n for n in FREEZE_FILES if n != GENERATED_MANIFEST]
        missing = [n for n in required_inputs if n not in files and n not in texts]
        if missing: raise RuntimeError(f"freeze missing {missing}")
        (root / GENERATED_MANIFEST).write_text("\n".join(manifest(root)) + "\n", encoding="utf-8")
        if destination.exists(): raise FileExistsError(destination)
        os.replace(root, destination)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target-repo", required=True)
    ap.add_argument("--target-ref", required=True)
    ap.add_argument("--target-path", required=True)
    ap.add_argument("--target-project", required=True)
    ap.add_argument("--classes", nargs="+", required=True)
    ap.add_argument("--freeze", type=Path, required=True)
    ap.add_argument("--ci-run-id")
    args = ap.parse_args()
    classes = tuple(sorted(set(args.classes)))
    if not set(classes) <= SUPPORTED_CLASSES: raise ValueError(f"unsupported classes: {set(classes) - SUPPORTED_CLASSES}")
    root = Path(__file__).resolve().parents[1]
    if subprocess.run(("git", "diff", "--quiet", "HEAD", "--", "src", "tests", "scripts/run_benchmark_005_blind.py"), cwd=root).returncode != 0:
        raise RuntimeError("CYDRA source/tests/runner must be clean before blind execution")
    runner_commit = git(root, "rev-parse", "HEAD")
    runner_blob = git(root, "rev-parse", "HEAD:scripts/run_benchmark_005_blind.py")

    with tempfile.TemporaryDirectory(prefix="cydra-b005-target-") as tmp:
        checkout = Path(tmp) / "target"
        clone_target(args.target_repo, args.target_ref, checkout)
        project = checkout / args.target_project
        source = checkout / args.target_path
        result = investigate(source, target=f"{args.target_repo}@{args.target_ref}")
        experiments = {e.hypothesis_id: e for e in result.experiments}
        statuses, executions, evidence = [], [], []
        for hypothesis in result.hypotheses:
            cls = INVARIANT_CLASS.get(hypothesis.invariant_id, "other")
            if cls not in classes: continue
            status = {"hypothesis_id": hypothesis.hypothesis_id, "class": cls, "extracted": True, "hypothesis_generated": True, "experiment_planned": hypothesis.hypothesis_id in experiments, "foundry_generated": False, "blind_executed": False, "classification": "NOT_REACHED"}
            if cls != "initialization":
                status["classification"] = "NOT_REACHED"
                status["blocked_reason"] = "Benchmark 005 current executable blind surface is initialization-only; non-initialization classes are recorded as capability gaps, not silently skipped."
                statuses.append(status); continue
            try:
                contract = contract_for(result, hypothesis)
                generated, execution, outcome = run_initialization(project, hypothesis, experiments[hypothesis.hypothesis_id], contract)
                status.update(foundry_generated=True, blind_executed=True, generated_path=str(generated), classification=outcome.benchmark_status, internal_status=outcome.internal_status, evidence=_json(outcome.evidence))
                executions.append(execution); evidence.append(outcome.evidence)
            except Exception as exc:
                status.update(failure_stage="execution_or_generation", blocked_reason=f"{type(exc).__name__}: {exc}")
            statuses.append(status)
        build = capture(project, "forge", "build")
        provenance = {"runner_commit": runner_commit, "runner_file_blob": runner_blob, "target_repo": args.target_repo, "target_ref": args.target_ref, "target_checkout_commit": git(checkout, "rev-parse", "HEAD"), "timestamp_utc": datetime.now(timezone.utc).isoformat(), "python_version": sys.version, "platform": platform.platform(), "ci_run_id": args.ci_run_id}
        classification = {"surface": "initialization-only", "hypotheses": statuses, "taxonomy": {"confirmed": "independently confirmed initialization candidate", "not_confirmed": "executed candidate did not confirm", "rule_gap": "relevant invariant/class absent from extraction", "pipeline_gap": "hypothesis generated but execution/classification could not complete", "capability_gap": "class outside current blind executable surface"}}
        execution_human = "\n\n".join(f"{e.experiment_id}: {e.status}\n{e.stdout}\n{e.stderr}" for e in executions)
        freeze({"provenance.json": provenance, "target-checkout.txt": git(checkout, "rev-parse", "HEAD") + "\n", "parse-output.json": {"target": result.target, "contracts": result.contracts, "selected_classes": classes}, "invariants.json": result.invariants, "hypotheses.json": result.hypotheses, "experiments.json": result.experiments, "execution.json": {"results": executions}, "integrity-check.json": {"runner_source_frozen": True, "forge_build": build}, "classification.json": classification}, {"execution-human.txt": execution_human, "compilation.log": json.dumps(build, indent=2) + "\n", "README.md": "Benchmark 005 blind Gavel freeze. Raw artifacts are frozen before any ground-truth lookup.\n"}, args.freeze)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
