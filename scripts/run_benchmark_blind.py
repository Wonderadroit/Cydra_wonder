from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from cydra.foundry import (
    ExecutionResult,
    generate_access_control_test,
    generate_initialization_test,
    require_executed,
    run_foundry_test,
    test_path_for,
)
from cydra.initialization_runtime import classify_initialization_execution
from cydra.pipeline import investigate

CYDRA_COMMIT = "8adf1ca1c8fd49fb7e04ca6d635b1e644e84bdcf"
SUPPORTED_CLASSES = {"authorization", "initialization", "arithmetic"}

CLASS_CAPABILITIES = {
    "authorization": {
        "extract": True,
        "generate_hypothesis": True,
        "plan_experiment": True,
        "generate_foundry": True,
        "execute_blind": True,
        "classify_blind": False,
        "classify_block_reason": "authorization classifier requires patched counterpart; blind target has none",
    },
    "initialization": {
        "extract": True,
        "generate_hypothesis": True,
        "plan_experiment": True,
        "generate_foundry": True,
        "execute_blind": True,
        "classify_blind": True,
        "classification_path": "single-sided initialization classifier",
    },
    "arithmetic": {
        "extract": True,
        "generate_hypothesis": True,
        "plan_experiment": True,
        "generate_foundry": False,
        "execute_blind": False,
        "classify_blind": False,
        "generate_block_reason": "arithmetic generator requires patched counterpart",
    },
}

INVARIANT_CLASS = {
    "INV-AUTH-001": "authorization",
    "INV-INIT-001": "initialization",
    "INV-ARITH-001": "arithmetic",
}

FREEZE_FILES = (
    "provenance.json",
    "target-checkout.txt",
    "parse-output.json",
    "invariants.json",
    "hypotheses.json",
    "experiments.json",
    "compilation.log",
    "execution.json",
    "execution-human.txt",
    "integrity-check.json",
    "classification.json",
    "manifest.sha256",
    "README.md",
)


def validate_classes(requested: list[str]) -> tuple[str, ...]:
    unsupported = set(requested) - SUPPORTED_CLASSES
    if unsupported:
        raise ValueError(
            f"Unsupported classes: {sorted(unsupported)}. Supported: {sorted(SUPPORTED_CLASSES)}"
        )
    return tuple(sorted(set(requested)))


def _json(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return {key: _json(item) for key, item in asdict(value).items()}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return [_json(item) for item in value]
    if isinstance(value, list):
        return [_json(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json(item) for key, item in value.items()}
    return value


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(_json(value), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _git_output(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", *args), cwd=cwd, text=True, capture_output=True, check=True
    )
    return completed.stdout.strip()


def require_frozen_source() -> None:
    root = Path(__file__).resolve().parents[1]
    source_diff = subprocess.run(
        ("git", "diff", "--quiet", CYDRA_COMMIT, "--", "src", "tests"),
        cwd=root,
        check=False,
    )
    if source_diff.returncode != 0:
        raise RuntimeError(f"CYDRA source/tests differ from frozen commit {CYDRA_COMMIT}")
    tracked = subprocess.run(
        ("git", "ls-files", "--error-unmatch", "scripts/run_benchmark_blind.py"),
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if tracked.returncode != 0:
        raise RuntimeError("run_benchmark_blind.py must be committed before execution")


def clone_target(repo: str, ref: str, destination: Path) -> None:
    subprocess.run(("git", "clone", "--no-tags", repo, str(destination)), check=True)
    subprocess.run(("git", "-C", str(destination), "checkout", "--detach", ref), check=True)


def _contract_for_hypothesis(result, hypothesis):
    for contract in result.contracts:
        if any(function.name == hypothesis.target_function for function in contract.functions):
            return contract
    raise RuntimeError(
        f"No contract model contains target function {hypothesis.target_function} "
        f"for {hypothesis.hypothesis_id}"
    )


def _target_import(contract, project: Path) -> str:
    return os.path.relpath(Path(contract.source), project).replace(os.sep, "/")


def _run_authorization(project: Path, hypothesis, experiment, contract) -> dict[str, Any]:
    output = test_path_for(project, f"generated/{hypothesis.hypothesis_id}.t.sol")
    generated = generate_access_control_test(
        hypothesis, _target_import(contract, project), contract.name, output
    )
    execution = run_foundry_test(project, generated, experiment.experiment_id, "blind")
    require_executed(execution)
    return {
        "generated_path": str(generated),
        "execution": execution,
        "classification": "NOT_REACHED",
        "classification_blocked_reason": CLASS_CAPABILITIES["authorization"]["classify_block_reason"],
    }


def _run_initialization(project: Path, hypothesis, experiment, contract) -> dict[str, Any]:
    output = test_path_for(project, f"generated/{hypothesis.hypothesis_id}.t.sol")
    generated = generate_initialization_test(
        hypothesis,
        _target_import(contract, project),
        contract.name,
        output,
        contract_model=contract,
    )
    execution = run_foundry_test(project, generated, experiment.experiment_id, "blind")
    require_executed(execution)
    outcome = classify_initialization_execution(hypothesis, execution)
    return {
        "generated_path": str(generated),
        "execution": execution,
        "classification": outcome.benchmark_status,
        "classification_path": CLASS_CAPABILITIES["initialization"]["classification_path"],
        "internal_status": outcome.internal_status,
        "evidence": outcome.evidence,
    }


def run_layers(result, project: Path, classes: tuple[str, ...]):
    experiments = {experiment.hypothesis_id: experiment for experiment in result.experiments}
    statuses: list[dict[str, Any]] = []
    executions: list[ExecutionResult] = []
    evidence: list[Any] = []

    for hypothesis in result.hypotheses:
        class_name = INVARIANT_CLASS.get(hypothesis.invariant_id)
        if class_name is None or class_name not in classes:
            continue
        capability = CLASS_CAPABILITIES[class_name]
        experiment = experiments[hypothesis.hypothesis_id]
        contract = _contract_for_hypothesis(result, hypothesis)
        status: dict[str, Any] = {
            "hypothesis_id": hypothesis.hypothesis_id,
            "class": class_name,
            "extracted": capability["extract"],
            "hypothesis_generated": capability["generate_hypothesis"],
            "experiment_planned": capability["plan_experiment"],
            "foundry_generated": False,
            "blind_executed": False,
            "classification": "NOT_REACHED",
        }

        if not capability["generate_foundry"]:
            status["foundry_generation_blocked_reason"] = capability["generate_block_reason"]
            statuses.append(status)
            continue

        if class_name == "authorization":
            run = _run_authorization(project, hypothesis, experiment, contract)
        elif class_name == "initialization":
            run = _run_initialization(project, hypothesis, experiment, contract)
        else:
            raise AssertionError(f"Unhandled supported class: {class_name}")

        status.update(
            {
                "foundry_generated": True,
                "blind_executed": True,
                "generated_path": run["generated_path"],
                "classification": run["classification"],
            }
        )
        for key in ("classification_blocked_reason", "classification_path", "internal_status"):
            if key in run:
                status[key] = run[key]
        executions.append(run["execution"])
        if "evidence" in run:
            evidence.append(run["evidence"])
        statuses.append(status)

    return statuses, executions, evidence


def _manifest(freeze: Path) -> list[str]:
    return [
        f"{hashlib.sha256((freeze / name).read_bytes()).hexdigest()}  {name}"
        for name in FREEZE_FILES
        if name != "manifest.sha256"
    ]


def create_freeze(files: dict[str, Any], text_files: dict[str, str], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="b006-a-freeze-", dir=destination.parent) as temp:
        freeze = Path(temp) / destination.name
        freeze.mkdir()
        for name, value in files.items():
            write_json(freeze / name, value)
        for name, text in text_files.items():
            (freeze / name).write_text(text, encoding="utf-8")
        missing = [
            name for name in FREEZE_FILES if name not in files and name not in text_files
        ]
        if missing:
            raise RuntimeError(f"Freeze missing files: {missing}")
        (freeze / "manifest.sha256").write_text(
            "\n".join(_manifest(freeze)) + "\n", encoding="utf-8"
        )
        if destination.exists():
            raise FileExistsError(destination)
        os.replace(freeze, destination)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run frozen CYDRA capability layers against a blind target."
    )
    parser.add_argument("--target-repo", required=True)
    parser.add_argument("--target-ref", required=True)
    parser.add_argument("--target-path", required=True)
    parser.add_argument("--target-project", required=True)
    parser.add_argument("--classes", nargs="+", required=True)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--ci-run-id")
    args = parser.parse_args()

    require_frozen_source()
    classes = validate_classes(args.classes)
    root = Path(__file__).resolve().parents[1]

    with tempfile.TemporaryDirectory(prefix="b006-a-target-") as temp:
        checkout = Path(temp) / "target"
        clone_target(args.target_repo, args.target_ref, checkout)
        project = checkout / args.target_project
        source = checkout / args.target_path
        result = investigate(source, target=f"{args.target_repo}@{args.target_ref}")
        statuses, executions, evidence = run_layers(result, project, classes)

        classification = {
            "surface": "initialization-only",
            "hypotheses": statuses,
            "outcome_taxonomy": {
                "initialization": {"TP": "confirmed", "FP": "rejected", "FN": "not_confirmed"},
                "authorization": "capability gap: differential-only classifier",
                "arithmetic": "capability gap: patched target required for generator",
                "accounting": "rule gap: absent from frozen executable pipeline",
                "other": "rule gap",
            },
        }
        provenance = {
            "cydra_commit": CYDRA_COMMIT,
            "runner_commit": _git_output(root, "rev-parse", "HEAD"),
            "target_repo": args.target_repo,
            "target_ref": args.target_ref,
            "target_checkout_commit": _git_output(checkout, "rev-parse", "HEAD"),
            "python_version": sys.version,
            "ci_run_id": args.ci_run_id,
        }
        create_freeze(
            {
                "provenance.json": provenance,
                "parse-output.json": {
                    "target": result.target,
                    "contracts": result.contracts,
                    "selected_classes": classes,
                },
                "invariants.json": result.invariants,
                "hypotheses.json": result.hypotheses,
                "experiments.json": result.experiments,
                "execution.json": {"results": executions},
                "integrity-check.json": {"runner_source_frozen": True},
                "classification.json": classification,
            },
            {
                "target-checkout.txt": _git_output(checkout, "rev-parse", "HEAD") + "\n",
                "compilation.log": "Compilation/execution evidence is retained in execution.json.\n",
                "execution-human.txt": "Human-readable Foundry stdout/stderr is retained in execution.json.\n",
                "README.md": "B006-A blind-target freeze. Frozen blind classification surface: initialization only.\n",
            },
            args.freeze,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
