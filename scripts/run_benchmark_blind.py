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

from cydra.compiler_state import CompilerEvidenceResult, compile_state_effects
from cydra.foundry import (
    ExecutionResult,
    generate_initialization_test,
    require_executed,
    run_foundry_test,
    test_path_for,
)
from cydra.initialization_runtime import classify_initialization_execution
from cydra.pipeline import investigate
from cydra.planned_foundry import generate_authorization_test_from_experiment
from cydra.reasoning import plan_access_control_experiment, plan_arithmetic_experiment, plan_initialization_experiment
from cydra.sequence_foundry import generate_sequence_test_from_experiment
from cydra.state_experiments import plan_cross_function_state_experiment
from cydra.structural_state import generate_cross_function_state_hypotheses

SUPPORTED_CLASSES = {"authorization", "initialization", "arithmetic", "state"}

CLASS_CAPABILITIES = {
    "state": {
        "extract": True,
        "generate_hypothesis": True,
        "plan_experiment": True,
        "generate_foundry": True,
        "execute_blind": True,
        "classify_blind": False,
        "classify_block_reason": "state sequence classification requires an independently verified relation and patched counterpart",
    },
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


def _command_capture(cwd: Path, *command: str) -> dict[str, Any]:
    completed = subprocess.run(
        command, cwd=cwd, text=True, capture_output=True, check=False
    )
    return {
        "command": list(command),
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "ok": completed.returncode == 0,
    }


def require_frozen_source() -> None:
    root = Path(__file__).resolve().parents[1]
    frozen_commit = _git_output(root, "rev-parse", "HEAD")
    source_diff = subprocess.run(
        ("git", "diff", "--quiet", frozen_commit, "--", "src", "tests"),
        cwd=root,
        check=False,
    )
    if source_diff.returncode != 0:
        raise RuntimeError(f"CYDRA source/tests differ from frozen commit {frozen_commit}")

    runner_path = Path(__file__).resolve()
    runner_diff = subprocess.run(
        ("git", "diff", "--quiet", frozen_commit, "--", str(runner_path.relative_to(root))),
        cwd=root,
        check=False,
    )
    if runner_diff.returncode != 0:
        raise RuntimeError("run_benchmark_blind.py differs from the frozen commit")

    untracked = subprocess.run(
        ("git", "status", "--porcelain", "--", str(runner_path.relative_to(root))),
        cwd=root,
        text=True,
        capture_output=True,
        check=True,
    )
    if untracked.stdout.strip():
        raise RuntimeError("run_benchmark_blind.py is not clean in git status")


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


def _failure_status(hypothesis, class_name: str, stage: str, error: Exception) -> dict[str, Any]:
    capability = CLASS_CAPABILITIES[class_name]
    status: dict[str, Any] = {
        "hypothesis_id": hypothesis.hypothesis_id,
        "class": class_name,
        "extracted": capability["extract"],
        "hypothesis_generated": capability["generate_hypothesis"],
        "experiment_planned": capability["plan_experiment"],
        "foundry_generated": stage not in {"generation"},
        "blind_executed": False,
        "classification": "NOT_REACHED",
        "failure_stage": stage,
        "blocked_reason": f"{type(error).__name__}: {error}",
    }
    if stage == "generation":
        status["foundry_generated"] = False
    elif stage == "execution":
        status["foundry_generated"] = True
    return status


def _run_authorization(project: Path, hypothesis, experiment, contract) -> dict[str, Any]:
    output = test_path_for(project, f"generated/{hypothesis.hypothesis_id}.t.sol")
    generated = generate_authorization_test_from_experiment(
        hypothesis,
        experiment,
        _target_import(contract, project),
        contract.name,
        output,
        contract,
    )
    execution = run_foundry_test(project, generated, experiment.experiment_id, "blind")
    require_executed(execution)
    return {
        "generated_path": str(generated),
        "execution": execution,
        "classification": "NOT_REACHED",
        "classification_blocked_reason": CLASS_CAPABILITIES["authorization"]["classify_block_reason"],
    }


def _run_state(project: Path, hypothesis, experiment, contract) -> dict[str, Any]:
    output = test_path_for(project, f"generated/{hypothesis.hypothesis_id}.t.sol")
    generated = generate_sequence_test_from_experiment(
        hypothesis, experiment, _target_import(contract, project), contract.name, output, contract
    )
    execution = run_foundry_test(project, generated, experiment.experiment_id, "blind")
    require_executed(execution)
    return {
        "generated_path": str(generated),
        "execution": execution,
        "classification": "NOT_REACHED",
        "classification_blocked_reason": CLASS_CAPABILITIES["state"]["classify_block_reason"],
    }

def _run_initialization(project: Path, hypothesis, experiment, contract) -> dict[str, Any]:
    output = test_path_for(project, f"generated/{hypothesis.hypothesis_id}.t.sol")
    generated = generate_initialization_test(
        hypothesis,
        _target_import(contract, project),
        contract.name,
        output,
        contract_model=contract,
        experiment=experiment,
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
        if class_name is None and hypothesis.invariant_id.startswith("INV-STATE-"):
            class_name = "state"
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

        try:
            if class_name == "authorization":
                run = _run_authorization(project, hypothesis, experiment, contract)
            elif class_name == "state":
                run = _run_state(project, hypothesis, experiment, contract)
            elif class_name == "initialization":
                run = _run_initialization(project, hypothesis, experiment, contract)
            else:
                raise AssertionError(f"Unhandled supported class: {class_name}")
        except Exception as error:
            stage = "generation" if not any(
                project.joinpath("test").rglob(f"{hypothesis.hypothesis_id}.t.sol")
            ) else "execution"
            statuses.append({**status, **_failure_status(hypothesis, class_name, stage, error)})
            continue

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


def _environment_provenance(root: Path, project: Path) -> tuple[dict[str, Any], str, str]:
    forge_version = _command_capture(project, "forge", "--version")
    forge_config = _command_capture(project, "forge", "config", "--json")
    pip_freeze = _command_capture(root, sys.executable, "-m", "pip", "freeze")
    dependency_text = pip_freeze["stdout"] if pip_freeze["ok"] else pip_freeze["stderr"]
    dependency_hash = hashlib.sha256(dependency_text.encode()).hexdigest()
    solc = None
    if forge_config["ok"]:
        try:
            config = json.loads(forge_config["stdout"])
            solc = config.get("solc") or config.get("solc_version")
        except json.JSONDecodeError:
            solc = None
    provenance = {
        "python_version": sys.version,
        "platform": platform.platform(),
        "dependencies": {
            "pip_freeze_sha256": dependency_hash,
            "pip_freeze_capture_ok": pip_freeze["ok"],
        },
        "foundry": {
            "version": forge_version["stdout"].strip() if forge_version["ok"] else None,
            "version_capture_ok": forge_version["ok"],
            "solidity_version": solc,
            "config_capture_ok": forge_config["ok"],
        },
    }
    return provenance, dependency_text, json.dumps(forge_config, indent=2, sort_keys=True)


def _blind_planner(hypothesis):
    if hypothesis.invariant_id.startswith("INV-STATE-"):
        return plan_cross_function_state_experiment(hypothesis)
    planners = {
        "INV-AUTH-001": plan_access_control_experiment,
        "INV-INIT-001": plan_initialization_experiment,
        "INV-ARITH-001": plan_arithmetic_experiment,
    }
    return planners[hypothesis.invariant_id](hypothesis)

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
    cydra_commit = _git_output(root, "rev-parse", "HEAD")

    with tempfile.TemporaryDirectory(prefix="b006-a-target-") as temp:
        checkout = Path(temp) / "target"
        clone_target(args.target_repo, args.target_ref, checkout)
        project = checkout / args.target_project
        source = checkout / args.target_path

        compiler_evidence: CompilerEvidenceResult = compile_state_effects(project, source)
        surfaces = (generate_cross_function_state_hypotheses,) if "state" in classes else ()
        result = investigate(
            source,
            target=f"{args.target_repo}@{args.target_ref}",
            semantic_evidence=compiler_evidence.evidence,
            constraint_evidence=compiler_evidence.constraints,
            experiment_planner=_blind_planner,
            reasoning_surfaces=surfaces,
        )
        statuses, executions, evidence = run_layers(result, project, classes)
        build_capture = _command_capture(project, "forge", "build")
        provenance_env, _, forge_config_text = _environment_provenance(root, project)

        classification = {
            "surface": "compiler-backed-planned-execution",
            "hypotheses": statuses,
            "outcome_taxonomy": {
                "initialization": {"TP": "confirmed", "FP": "rejected", "FN": "not_confirmed"},
                "authorization": {"execution": "measured", "classification": "requires_patched_counterpart"},
                "arithmetic": {"execution": "capability_gap"},
            },
        }
        by_class: dict[str, dict[str, int | bool | str]] = {}
        for class_name in classes:
            class_statuses = [status for status in statuses if status["class"] == class_name]
            extracted = sum(1 for status in class_statuses if status.get("extracted"))
            executed = sum(1 for status in class_statuses if status.get("blind_executed"))
            if extracted == 0:
                class_status = "no_candidate_extracted"
            elif executed == extracted:
                class_status = "executed"
            else:
                class_status = "capability_gap"
            by_class[class_name] = {
                "requested": True,
                "hypotheses_extracted": extracted,
                "hypotheses_executed": executed,
                "status": class_status,
            }
        classification["class_coverage"] = by_class
        classification["taxonomy"] = {
            "confirmed": "independently confirmed initialization candidate",
            "not_confirmed": "executed candidate did not confirm",
            "no_candidate_extracted": "requested class produced no hypothesis under the current reasoning rules",
            "capability_gap": "class was extracted but executable coverage was incomplete",
            "pipeline_gap": "hypothesis generated but execution/classification could not complete",
            "rule_gap": "relevant invariant/class absent from extraction",
        }

        execution_json = {
            "compiler_evidence": _json(compiler_evidence),
            "executions": [_json(execution) for execution in executions],
            "evidence": _json(evidence),
            "build": build_capture,
        }
        execution_human = "\n\n".join(
            f"{execution.experiment_id}: {execution.status} executed={execution.executed} "
            f"tests_run={execution.tests_run} tests_failed={execution.tests_failed}\n"
            f"$ {' '.join(execution.command)}\n{execution.stdout}\n{execution.stderr}"
            for execution in executions
        )
        provenance = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "target_repo": args.target_repo,
            "target_ref": args.target_ref,
            "target_path": args.target_path,
            "target_project": args.target_project,
            "classes": list(classes),
            "cydra_commit": cydra_commit,
            "environment": provenance_env,
        }
        text_files = {
            "target-checkout.txt": _git_output(checkout, "rev-parse", "HEAD") + "\n",
            "compilation.log": json.dumps(
                {"compiler_evidence": _json(compiler_evidence), "build": build_capture},
                indent=2,
                sort_keys=True,
            ) + "\n",
            "execution-human.txt": execution_human,
            "README.md": (
                "# CYDRA blind capability artifact\n\n"
                "This artifact records compiler-backed constraints, structural hypotheses, "
                "planned experiment inputs, generated experiments, execution evidence, "
                "and explicit capability gaps. A measured execution is not itself a "
                "vulnerability confirmation.\n"
            ),
            "integrity-check.json": json.dumps({"manifest": "manifest.sha256"}, indent=2) + "\n",
            "forge-config.json": forge_config_text,
        }
        files = {
            "provenance.json": provenance,
            "parse-output.json": {"target": args.target_path, "contracts": _json(result.contracts)},
            "invariants.json": result.invariants,
            "hypotheses.json": result.hypotheses,
            "experiments.json": result.experiments,
            "execution.json": execution_json,
            "classification.json": classification,
        }
        create_freeze(files, text_files, args.freeze)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
