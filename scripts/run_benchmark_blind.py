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

from cydra.foundry import (
    ExecutionResult,
    generate_access_control_test,
    generate_arithmetic_foundry_test,
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
            f"Unsupported classes: {sorted(unsupported)}. "
            f"Supported: {sorted(SUPPORTED_CLASSES)}"
        )
    return tuple(sorted(set(requested)))


def preflight_validate(args: argparse.Namespace) -> None:
    if (args.patched_path is None) != (args.patched_contract is None):
        raise ValueError(
            "--patched-path and --patched-contract must be provided together"
        )

    for value, name in (
        (args.target_path, "--target-path"),
        (args.target_contract, "--target-contract"),
        (args.patched_path, "--patched-path"),
        (args.patched_contract, "--patched-contract"),
    ):
        if value is not None and ":" in value:
            raise ValueError(
                f"{name} contains a colon: '{value}'. "
                "The target specification format '<path>:<contract>' "
                "cannot represent values containing ':'."
            )

    if not args.target_path:
        raise ValueError("--target-path is required")

    if not args.target_contract:
        raise ValueError("--target-contract is required")

    if not args.target_project:
        raise ValueError("--target-project is required")

    if not args.target_repo:
        raise ValueError("--target-repo is required")

    if not args.target_ref:
        raise ValueError("--target-ref is required")

    if not args.classes:
        raise ValueError("--classes is required")


def get_capability(class_name: str, has_patched_target: bool) -> dict[str, Any]:
    if class_name == "authorization":
        capability = dict(CLASS_CAPABILITIES[class_name])
        capability["classify_blind"] = has_patched_target
        if not has_patched_target:
            capability["classify_block_reason"] = (
                "authorization classifier requires patched counterpart; "
                "blind target has none"
            )
        return capability

    if class_name == "initialization":
        return dict(CLASS_CAPABILITIES[class_name])

    if class_name == "arithmetic":
        capability = dict(CLASS_CAPABILITIES[class_name])
        capability["generate_foundry"] = has_patched_target
        capability["execute_blind"] = has_patched_target
        capability["classify_blind"] = False
        if has_patched_target:
            capability.pop("generate_block_reason", None)
        return capability

    raise ValueError(f"Unsupported class: {class_name}")


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
    path.write_text(
        json.dumps(_json(value), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _git_output(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", *args),
        cwd=cwd,
        text=True,
        capture_output=True,
        check=True,
    )
    return completed.stdout.strip()


def _command_capture(cwd: Path, *command: str) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
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
    source_diff = subprocess.run(
        ("git", "diff", "--quiet", CYDRA_COMMIT, "--", "src", "tests"),
        cwd=root,
        check=False,
    )
    if source_diff.returncode != 0:
        raise RuntimeError(
            f"CYDRA source/tests differ from frozen commit {CYDRA_COMMIT}"
        )

    runner_path = Path(__file__).resolve()
    runner_diff = subprocess.run(
        (
            "git",
            "diff",
            "--quiet",
            "HEAD",
            "--",
            str(runner_path.relative_to(root)),
        ),
        cwd=root,
        check=False,
    )
    if runner_diff.returncode != 0:
        raise RuntimeError("run_benchmark_blind.py has uncommitted changes")

    untracked = subprocess.run(
        (
            "git",
            "status",
            "--porcelain",
            "--",
            str(runner_path.relative_to(root)),
        ),
        cwd=root,
        text=True,
        capture_output=True,
        check=True,
    )
    if untracked.stdout.strip():
        raise RuntimeError("run_benchmark_blind.py is not clean in git status")


def clone_target(repo: str, ref: str, destination: Path) -> None:
    subprocess.run(
        ("git", "clone", "--no-tags", repo, str(destination)),
        check=True,
    )
    subprocess.run(
        ("git", "-C", str(destination), "checkout", "--detach", ref),
        check=True,
    )


def _contract_for_hypothesis(result, hypothesis):
    for contract in result.contracts:
        if any(
            function.name == hypothesis.target_function
            for function in contract.functions
        ):
            return contract
    raise RuntimeError(
        f"No contract model contains target function "
        f"{hypothesis.target_function} for {hypothesis.hypothesis_id}"
    )


def _target_import(contract, project: Path) -> str:
    return os.path.relpath(
        Path(contract.source),
        project,
    ).replace(os.sep, "/")


def _execution_result(execution: ExecutionResult) -> dict[str, Any]:
    return {
        "status": execution.status,
        "tests_run": execution.tests_run,
        "tests_failed": execution.tests_failed,
        "exit_code": execution.exit_code,
    }


def _failure_status(
    hypothesis,
    class_name: str,
    error: Exception,
    capability: dict[str, Any],
    generation_attempted: bool,
    generation_failed: bool,
    execution_attempted: bool,
    execution_failed: bool,
) -> dict[str, Any]:
    status: dict[str, Any] = {
        "hypothesis_id": hypothesis.hypothesis_id,
        "class": class_name,
        "extracted": capability["extract"],
        "hypothesis_generated": capability["generate_hypothesis"],
        "experiment_planned": capability["plan_experiment"],
        "foundry_generated": (
            generation_attempted and not generation_failed
        ),
        "blind_executed": (
            execution_attempted and not execution_failed
        ),
        "classification": "NOT_REACHED",
        "generation_attempted": generation_attempted,
        "execution_attempted": execution_attempted,
        "failure_stage": (
            "generation"
            if generation_failed
            else "execution"
            if execution_failed
            else "unknown"
        ),
        "blocked_reason": f"{type(error).__name__}: {error}",
    }

    if generation_failed:
        status["foundry_generation_blocked_reason"] = (
            f"{type(error).__name__}: {error}"
        )

    return status


def _run_authorization(
    project: Path,
    hypothesis,
    experiment,
    contract,
    attempts: dict[str, bool],
) -> dict[str, Any]:
    output = test_path_for(
        project,
        f"generated/{hypothesis.hypothesis_id}.t.sol",
    )

    attempts["generation_attempted"] = True
    generated = generate_access_control_test(
        hypothesis,
        _target_import(contract, project),
        contract.name,
        output,
    )

    attempts["execution_attempted"] = True
    execution = run_foundry_test(
        project,
        generated,
        experiment.experiment_id,
        "blind",
    )
    require_executed(execution)
    return {
        "generated_path": str(generated),
        "execution": execution,
        "classification": "NOT_REACHED",
        "classification_blocked_reason": (
            "authorization classifier requires patched counterpart; "
            "blind target has none"
        ),
    }


def _run_initialization(
    project: Path,
    hypothesis,
    experiment,
    contract,
    attempts: dict[str, bool],
) -> dict[str, Any]:
    output = test_path_for(
        project,
        f"generated/{hypothesis.hypothesis_id}.t.sol",
    )

    attempts["generation_attempted"] = True
    generated = generate_initialization_test(
        hypothesis,
        _target_import(contract, project),
        contract.name,
        output,
        contract_model=contract,
    )

    attempts["execution_attempted"] = True
    execution = run_foundry_test(
        project,
        generated,
        experiment.experiment_id,
        "blind",
    )
    require_executed(execution)
    outcome = classify_initialization_execution(
        hypothesis,
        execution,
    )
    return {
        "generated_path": str(generated),
        "execution": execution,
        "classification": outcome.benchmark_status,
        "classification_path": (
            "single-sided initialization classifier"
        ),
        "internal_status": outcome.internal_status,
        "evidence": outcome.evidence,
    }


def _run_arithmetic(
    project: Path,
    hypothesis,
    experiment,
    target_spec: str,
    patched_spec: str,
    attempts: dict[str, bool],
) -> dict[str, Any]:
    attempts["generation_attempted"] = True
    generated = generate_arithmetic_foundry_test(
        experiment,
        target_spec,
        patched_spec,
    )

    attempts["execution_attempted"] = True
    execution = run_foundry_test(
        project,
        generated,
        experiment.experiment_id,
        "blind",
    )
    require_executed(execution)
    return {
        "generated_path": str(generated),
        "execution": execution,
        "classification": "NOT_REACHED",
        "classification_blocked_reason": (
            "arithmetic classifier is not implemented in the "
            "frozen executable pipeline"
        ),
    }


def run_layers(
    result,
    project: Path,
    classes: tuple[str, ...],
    target_path: str,
    target_contract: str,
    patched_path: str | None,
    patched_contract: str | None,
):
    has_patched_target = (
        patched_path is not None
        and patched_contract is not None
    )

    target_spec = f"{target_path}:{target_contract}"
    patched_spec = (
        f"{patched_path}:{patched_contract}"
        if has_patched_target
        else None
    )

    experiments = {
        experiment.hypothesis_id: experiment
        for experiment in result.experiments
    }
    statuses: list[dict[str, Any]] = []
    executions: list[ExecutionResult] = []
    evidence: list[Any] = []

    for hypothesis in result.hypotheses:
        class_name = INVARIANT_CLASS.get(hypothesis.invariant_id)
        if class_name is None or class_name not in classes:
            continue

        capability = get_capability(
            class_name,
            has_patched_target,
        )
        experiment = experiments[hypothesis.hypothesis_id]
        contract = _contract_for_hypothesis(
            result,
            hypothesis,
        )

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
            status["foundry_generation_blocked_reason"] = capability[
                "generate_block_reason"
            ]
            statuses.append(status)
            continue

        attempts = {
            "generation_attempted": False,
            "generation_failed": False,
            "execution_attempted": False,
            "execution_failed": False,
        }

        try:
            if class_name == "authorization":
                run = _run_authorization(
                    project,
                    hypothesis,
                    experiment,
                    contract,
                    attempts,
                )
            elif class_name == "initialization":
                run = _run_initialization(
                    project,
                    hypothesis,
                    experiment,
                    contract,
                    attempts,
                )
            elif class_name == "arithmetic":
                if patched_spec is None:
                    raise AssertionError(
                        "Arithmetic execution reached without "
                        "a patched target"
                    )
                run = _run_arithmetic(
                    project,
                    hypothesis,
                    experiment,
                    target_spec,
                    patched_spec,
                    attempts,
                )
            else:
                raise AssertionError(
                    f"Unhandled supported class: {class_name}"
                )
        except Exception as error:
            if attempts["generation_attempted"] and not attempts[
                "execution_attempted"
            ]:
                attempts["generation_failed"] = True
            elif attempts["execution_attempted"]:
                attempts["execution_failed"] = True

            statuses.append(
                {
                    **status,
                    **_failure_status(
                        hypothesis,
                        class_name,
                        error,
                        capability,
                        attempts["generation_attempted"],
                        attempts["generation_failed"],
                        attempts["execution_attempted"],
                        attempts["execution_failed"],
                    ),
                }
            )
            continue

        execution = run["execution"]

        status.update(
            {
                "foundry_generated": (
                    attempts["generation_attempted"]
                    and not attempts["generation_failed"]
                ),
                "blind_executed": (
                    capability["execute_blind"]
                    and attempts["execution_attempted"]
                    and not attempts["execution_failed"]
                ),
                "generated_path": run["generated_path"],
                "classification": run["classification"],
                "generation_attempted": attempts["generation_attempted"],
                "execution_attempted": attempts["execution_attempted"],
            }
        )

        if execution is not None:
            status["execution_result"] = _execution_result(
                execution
            )

        for key in (
            "classification_blocked_reason",
            "classification_path",
            "internal_status",
        ):
            if key in run:
                status[key] = run[key]

        if capability.get("classify_block_reason"):
            status["classification_blocked_reason"] = capability[
                "classify_block_reason"
            ]

        if capability.get("generate_block_reason"):
            status["foundry_generation_blocked_reason"] = capability[
                "generate_block_reason"
            ]

        executions.append(execution)

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


def create_freeze(
    files: dict[str, Any],
    text_files: dict[str, str],
    destination: Path,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="b006-a-freeze-",
        dir=destination.parent,
    ) as temp:
        freeze = Path(temp) / destination.name
        freeze.mkdir()

        for name, value in files.items():
            write_json(freeze / name, value)

        for name, text in text_files.items():
            (freeze / name).write_text(
                text,
                encoding="utf-8",
            )

        missing = [
            name
            for name in FREEZE_FILES
            if name != "manifest.sha256"
            and name not in files
            and name not in text_files
        ]
        if missing:
            raise RuntimeError(
                f"Freeze missing files: {missing}"
            )

        (freeze / "manifest.sha256").write_text(
            "\n".join(_manifest(freeze)) + "\n",
            encoding="utf-8",
        )

        if destination.exists():
            raise FileExistsError(destination)

        os.replace(freeze, destination)


def _environment_provenance(
    root: Path,
    project: Path,
) -> tuple[dict[str, Any], str, str]:
    forge_version = _command_capture(
        project,
        "forge",
        "--version",
    )
    forge_config = _command_capture(
        project,
        "forge",
        "config",
        "--json",
    )
    pip_freeze = _command_capture(
        root,
        sys.executable,
        "-m",
        "pip",
        "freeze",
    )

    dependency_text = (
        pip_freeze["stdout"]
        if pip_freeze["ok"]
        else pip_freeze["stderr"]
    )
    dependency_hash = hashlib.sha256(
        dependency_text.encode()
    ).hexdigest()

    solc = None
    if forge_config["ok"]:
        try:
            config = json.loads(
                forge_config["stdout"]
            )
            solc = config.get("solc") or config.get(
                "solc_version"
            )
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
            "version": (
                forge_version["stdout"].strip()
                if forge_version["ok"]
                else None
            ),
            "version_capture_ok": forge_version["ok"],
            "solidity_version": solc,
            "config_capture_ok": forge_config["ok"],
        },
    }

    return (
        provenance,
        dependency_text,
        json.dumps(
            forge_config,
            indent=2,
            sort_keys=True,
        ),
    )


def _load_config(path: Path) -> dict[str, Any]:
    with path.open(
        "r",
        encoding="utf-8",
    ) as handle:
        value = json.load(handle)

    if not isinstance(value, dict):
        raise ValueError(
            f"Config must contain a JSON object: {path}"
        )

    return value


def _resolve_args(args: argparse.Namespace) -> argparse.Namespace:
    if args.config is not None:
        config = _load_config(args.config)

        if args.target_repo is None:
            args.target_repo = config.get("target_repo")
        if args.target_ref is None:
            args.target_ref = config.get("target_ref")
        if args.target_path is None:
            args.target_path = config.get("target_path")
        if args.target_contract is None:
            args.target_contract = config.get("target_contract")
        if args.target_project is None:
            args.target_project = config.get("target_project")
        if args.patched_path is None:
            args.patched_path = config.get("patched_path")
        if args.patched_contract is None:
            args.patched_contract = config.get(
                "patched_contract"
            )
        if args.classes is None:
            args.classes = config.get("classes")
        if args.freeze is None and config.get("freeze"):
            args.freeze = Path(config["freeze"])

    if args.output is not None:
        args.freeze = args.output / "freeze"

    return args


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run frozen CYDRA capability layers "
            "against a blind target."
        )
    )

    parser.add_argument("--config", type=Path)

    parser.add_argument("--target-repo")
    parser.add_argument("--target-ref")
    parser.add_argument("--target-path")
    parser.add_argument("--target-contract")
    parser.add_argument("--target-project")

    parser.add_argument("--patched-path")
    parser.add_argument("--patched-contract")

    parser.add_argument(
        "--classes",
        nargs="+",
    )

    parser.add_argument(
        "--freeze",
        type=Path,
    )

    parser.add_argument(
        "--output",
        type=Path,
    )

    parser.add_argument("--ci-run-id")

    args = parser.parse_args()
    args = _resolve_args(args)

    preflight_validate(args)

    if args.freeze is None:
        raise ValueError(
            "--freeze or --output is required"
        )

    require_frozen_source()

    classes = validate_classes(args.classes)
    root = Path(__file__).resolve().parents[1]

    with tempfile.TemporaryDirectory(
        prefix="b006-a-target-"
    ) as temp:
        checkout = Path(temp) / "target"

        clone_target(
            args.target_repo,
            args.target_ref,
            checkout,
        )

        project = checkout / args.target_project
        source = checkout / args.target_path

        result = investigate(
            source,
            target=f"{args.target_repo}@{args.target_ref}",
        )

        statuses, executions, evidence = run_layers(
            result,
            project,
            classes,
            args.target_path,
            args.target_contract,
            args.patched_path,
            args.patched_contract,
        )

        build_capture = _command_capture(
            project,
            "forge",
            "build",
        )

        provenance_env, _, forge_config_text = (
            _environment_provenance(
                root,
                project,
            )
        )

        classification = {
            "surface": {
                "extraction": [
                    "authorization",
                    "initialization",
                    "arithmetic",
                ],
                "classification": [
                    "initialization",
                ],
            },
            "hypotheses": statuses,
            "outcome_taxonomy": {
                "initialization": {
                    "TP": "confirmed",
                    "FP": "rejected",
                    "FN": "not_confirmed",
                },
                "authorization": (
                    "context-dependent differential "
                    "classification"
                ),
                "arithmetic": (
                    "execution supported with patched "
                    "counterpart; classification not reached"
                ),
                "accounting": (
                    "rule gap: absent from frozen "
                    "executable pipeline"
                ),
                "other": "rule gap",
            },
        }

        runner_commit = _git_output(
            root,
            "rev-parse",
            "HEAD",
        )
        runner_blob = _git_output(
            root,
            "rev-parse",
            "HEAD:scripts/run_benchmark_blind.py",
        )

        provenance = {
            "cydra_commit": CYDRA_COMMIT,
            "runner_commit": runner_commit,
            "runner_file_blob": runner_blob,
            "target_repo": args.target_repo,
            "target_ref": args.target_ref,
            "target_checkout_commit": _git_output(
                checkout,
                "rev-parse",
                "HEAD",
            ),
            "timestamp_utc": datetime.now(
                timezone.utc
            ).isoformat(),
            "ci_run_id": args.ci_run_id,
            "config": (
                str(args.config)
                if args.config is not None
                else None
            ),
            "output": (
                str(args.output)
                if args.output is not None
                else None
            ),
            **provenance_env,
        }

        execution_human = []

        for item in executions:
            execution_human.append(
                f"=== {item.experiment_id} / "
                f"{item.target} ===\n"
                f"command: {' '.join(item.command)}\n"
                f"exit_code: {item.exit_code}\n"
                f"status: {item.status}\n"
                f"tests_run: {item.tests_run}\n"
                f"tests_failed: {item.tests_failed}\n"
                f"--- stdout ---\n{item.stdout}\n"
                f"--- stderr ---\n{item.stderr}\n"
            )

        integrity = {
            "runner_source_frozen": True,
            "runner_commit": runner_commit,
            "runner_file_blob": runner_blob,
            "cydra_commit": CYDRA_COMMIT,
            "forge_build_exit_code": build_capture[
                "exit_code"
            ],
            "forge_build_ok": build_capture["ok"],
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
                "execution.json": {
                    "results": executions,
                    "evidence": evidence,
                },
                "integrity-check.json": integrity,
                "classification.json": classification,
            },
            {
                "target-checkout.txt": (
                    _git_output(
                        checkout,
                        "rev-parse",
                        "HEAD",
                    )
                    + "\n"
                ),
                "compilation.log": (
                    "$ forge build\n"
                    f"{build_capture['stdout']}"
                    f"{build_capture['stderr']}"
                    "\n\n=== forge config --json ===\n"
                    f"{forge_config_text}\n"
                ),
                "execution-human.txt": "\n".join(
                    execution_human
                ),
                "README.md": (
                    "B006-A blind-target freeze. "
                    "Frozen blind classification surface: "
                    "initialization only.\n"
                ),
            },
            args.freeze,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
