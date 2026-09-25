from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, replace
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
from cydra.authorization_runtime import classify_authorization_blind_execution
from cydra.pipeline import ReasoningContribution, _default_experiment_planner, investigate
from cydra.planned_foundry import generate_authorization_test_from_experiment
from cydra.reasoning import plan_access_control_experiment, plan_arithmetic_experiment, plan_initialization_experiment, plan_guard_parity_experiment
from cydra.sequence_foundry import generate_sequence_test_from_experiment
from cydra.state_experiments import plan_cross_function_state_experiment
from cydra.structural_state import generate_cross_function_state_hypotheses
from cydra.target_adapter import inspect_target
from cydra.execution_readiness import constructible_state_setup_plan, inspect_execution_readiness, role_address_expression
from cydra.prerequisite_graph import apply_observations, build_prerequisite_graph, can_enter_security_experiment
from cydra.runtime_observation import plan_public_state_observations
from cydra.runtime_observation_evidence import evidence_records_from_execution, observations_from_execution
from cydra.state_relation_observation import plan_state_relation_observations
from cydra.state_relation_evidence import evidence_records_from_relation_execution
from cydra.structural_pair_symmetry import generate_pair_symmetry_hypotheses
from cydra.structural_aggregation_order import generate_aggregation_order_hypotheses
from cydra.structural_configuration_binding import generate_configuration_binding_hypotheses
from cydra.guard_parity_execution import generate_guard_parity_test

SUPPORTED_CLASSES = {"authorization", "initialization", "arithmetic", "state", "guard_parity"}

CLASS_CAPABILITIES = {
    "guard_parity": {
        "extract": True,
        "generate_hypothesis": True,
        "plan_experiment": True,
        "generate_foundry": True,
        "execute_blind": True,
        "classify_blind": False,
        "classify_block_reason": "guard-parity differential classification requires a patched counterpart",
    },
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
        "classify_blind": True,
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
    "INV-PAIR-SYMMETRY-001": "arithmetic",
    "INV-AGGREGATION-ORDER-001": "arithmetic",
    "INV-CONFIG-BINDING-001": "state",
}

FREEZE_FILES = (
    "provenance.json",
    "target-intake.json",
    "execution-readiness.json",
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
    subprocess.run(("git", "clone", "--no-tags", "--recurse-submodules", repo, str(destination)), check=True)
    subprocess.run(("git", "-C", str(destination), "checkout", "--detach", ref), check=True)


def _materialize_generic_foundry_config(project: Path) -> None:
    """Make npm/Hardhat Solidity checkouts consumable by the generic Foundry harness."""
    config = project / "foundry.toml"
    if not config.exists():
        source_dir = "contracts" if (project / "contracts").exists() else "src"
        config.write_text(
            "[profile.default]\n"
            f'src = "{source_dir}"\n'
            'test = "test"\n'
            'libs = ["lib", "node_modules"]\n'
            'optimizer = false\n'
            'via_ir = false\n',
            encoding="utf-8",
        )
    remappings = project / "remappings.txt"
    if remappings.exists():
        return
    node_modules = project / "node_modules"
    mappings: list[str] = []
    if node_modules.exists():
        for child in sorted(node_modules.iterdir()):
            if child.name.startswith("."):
                continue
            if child.name.startswith("@") and child.is_dir():
                for package in sorted(child.iterdir()):
                    if package.is_dir():
                        mappings.append(f"{child.name}/{package.name}=node_modules/{child.name}/{package.name}/")
            elif child.is_dir():
                mappings.append(f"{child.name}=node_modules/{child.name}/")
    if mappings:
        remappings.write_text("\n".join(mappings) + "\n", encoding="utf-8")


def prepare_target_project(project: Path) -> None:
    """Materialize declared dependencies needed by the generic experiment harness."""
    package = project / "package.json"
    if package.exists():
        # Prefer an npm lockfile when both lockfiles exist. Some audit targets
        # retain a stale yarn.lock beside the authoritative package-lock.json;
        # frozen Yarn then fails before CYDRA can inspect the target.
        if (project / "package-lock.json").exists():
            command = ("npm", "ci", "--ignore-scripts")
        elif (project / "yarn.lock").exists():
            command = ("yarn", "install", "--frozen-lockfile", "--ignore-scripts", "--ignore-engines")
        else:
            command = ("npm", "install", "--ignore-scripts")
        # Historical target dependency installation can fail transiently on
        # registry/network access. Retry the exact frozen dependency command a
        # small bounded number of times; never change the lockfile semantics or
        # fall back to a different dependency resolver.
        last_error: subprocess.CalledProcessError | None = None
        for attempt in range(3):
            try:
                environment = None
                if command and command[0] == "yarn":
                    environment = os.environ.copy()
                    environment["YARN_CACHE_FOLDER"] = str(project / ".cydra-yarn-cache")
                subprocess.run(command, cwd=project, check=True, env=environment)
                break
            except subprocess.CalledProcessError as error:
                last_error = error
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)
        if last_error is not None and attempt == 2:
            raise last_error

    # Generated Foundry experiments import forge-std/Test.sol. Materialize
    # the standard library only when the target does not already vendor it.
    forge_std = project / "lib" / "forge-std"
    if not forge_std.exists():
        subprocess.run(
            ("forge", "install", "foundry-rs/forge-std", "--no-commit"),
            cwd=project,
            check=True,
        )

    # Hardhat/npm targets are accepted by target intake and need a temporary
    # Foundry execution envelope. Never overwrite a target-authored config.
    if not (project / "foundry.toml").exists():
        _materialize_generic_foundry_config(project)


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
    outcome = classify_authorization_blind_execution(hypothesis, execution)
    return {
        "generated_path": str(generated),
        "execution": execution,
        "classification": outcome.benchmark_status,
        "classification_path": "single-sided authorization invariant classifier",
        "internal_status": outcome.internal_status,
        "execution_status": execution.status,
        "execution_executed": execution.executed,
        "tests_run": execution.tests_run,
        "tests_failed": execution.tests_failed,
        "evidence": outcome.evidence,
    }


def _setup_argument(function, index: int, role: str | None) -> str:
    parameter = function.parameters[index]
    parameter_type = parameter.type.strip()
    base = parameter_type.split()[0].rstrip("[]")
    if parameter_type.endswith("[]"):
        raise ValueError(f"unsupported setup array parameter type: {parameter.type}")
    if base == "address":
        if role:
            expression = role_address_expression(role)
            if expression:
                return expression
        name = parameter.name.lower()
        if "recipient" in name or "user" in name or "account" in name:
            return "attacker"
        return "attacker"
    if parameter_type == "address payable":
        return "payable(attacker)"
    if base == "bool":
        return "true"
    if base.startswith(("uint", "int")):
        return "1"
    if base == "string":
        return '"CYDRA"'
    if base == "bytes":
        return 'bytes("")'
    if base.startswith("bytes") and base[5:].isdigit():
        return "0"
    raise ValueError(f"unsupported setup parameter type: {parameter.type}")


def _setup_steps(contract, setup_actions):
    functions = {item.name: item for item in (*contract.functions, *contract.inherited_functions)}
    steps = []
    for action in setup_actions:
        function = functions.get(action.function)
        if function is None:
            raise ValueError(f"setup action is not modeled: {action.function}")
        arguments = tuple(
            _setup_argument(function, index, action.caller_role)
            for index in range(len(function.parameters))
        )
        from cydra.models import ExperimentStep
        steps.append(ExperimentStep(function=function.name, arguments=arguments))
    return tuple(steps)


def _run_state_prerequisite_observation(
    project: Path,
    hypothesis,
    experiment,
    contract,
    setup_actions,
    plans,
) -> tuple[Any, tuple[Any, ...], tuple[Any, ...]]:
    if not plans:
        raise ValueError("state prerequisite has no deterministic public runtime observation")
    from cydra.models import ExperimentStep
    setup_steps = _setup_steps(contract, setup_actions)
    functions = {item.name: item for item in (*contract.functions, *contract.inherited_functions)}
    target_function = functions.get(hypothesis.target_function)
    if target_function is None:
        raise ValueError(f"state target function is not modeled: {hypothesis.target_function}")
    target_arguments = tuple(_setup_argument(target_function, i, None) for i in range(len(target_function.parameters)))
    observation_steps = (*setup_steps, ExperimentStep(function=hypothesis.target_function, arguments=target_arguments))
    observation_experiment = replace(experiment, experiment_id=f"{experiment.experiment_id}-PREREQ", steps=observation_steps)
    output = test_path_for(project, f"generated/{hypothesis.hypothesis_id}-prereq.t.sol")
    generated = generate_sequence_test_from_experiment(
        hypothesis,
        observation_experiment,
        _target_import(contract, project),
        contract.name,
        output,
        contract,
        verify_state_prerequisites=True,
        stop_before_target=True,
    )
    execution = run_foundry_test(project, generated, observation_experiment.experiment_id, "prerequisite")
    observations = observations_from_execution(observation_experiment.experiment_id, plans, execution)
    evidence = evidence_records_from_execution(observation_experiment.experiment_id, plans, execution)
    return execution, observations, evidence


def _run_state_relation_verification(
    project: Path,
    hypothesis,
    experiment,
    contract,
) -> tuple[Any, tuple[Any, ...], tuple[Any, ...]]:
    """Verify a source-backed state transition before any state classification."""
    function = next(
        (item for item in (*contract.functions, *contract.inherited_functions)
         if item.name == hypothesis.target_function),
        None,
    )
    if function is None:
        raise ValueError(f"state relation target function is not modeled: {hypothesis.target_function}")
    # Verify every externally callable transition in the ordered experiment,
    # not only the hypothesis target. This makes the evidence chain genuinely
    # before/between/after for cross-function state hypotheses.
    functions = {
        item.name: item for item in (*contract.functions, *contract.inherited_functions)
    }
    relation_plans_by_step = []
    for step in experiment.steps:
        step_function = functions.get(step.function)
        if step_function is None:
            raise ValueError(f"state relation step is not modeled: {step.function}")
        step_plans = plan_state_relation_observations(contract, step_function)
        if step_function.writes and not step_plans:
            raise ValueError(
                f"state transition {step_function.name} has no deterministic "
                "public unsigned-integer relation observation"
            )
        relation_plans_by_step.extend(step_plans)
    plans = tuple(relation_plans_by_step)
    if not plans:
        raise ValueError(
            "state experiment has no deterministic public unsigned-integer relation observation"
        )
    output = test_path_for(
        project, f"generated/{hypothesis.hypothesis_id}-relation.t.sol"
    )
    relation_experiment = replace(
        experiment,
        experiment_id=f"{experiment.experiment_id}-RELATION",
    )
    generated = generate_sequence_test_from_experiment(
        hypothesis,
        relation_experiment,
        _target_import(contract, project),
        contract.name,
        output,
        contract,
        verify_state_relations=True,
        verify_state_relations_all_steps=True,
    )
    execution = run_foundry_test(
        project, generated, relation_experiment.experiment_id, "relation"
    )
    evidence = evidence_records_from_relation_execution(
        relation_experiment.experiment_id, plans, execution
    )
    return execution, plans, evidence


def _run_state(project: Path, hypothesis, experiment, contract) -> dict[str, Any]:
    output = test_path_for(project, f"generated/{hypothesis.hypothesis_id}.t.sol")
    generated = generate_sequence_test_from_experiment(
        hypothesis, experiment, _target_import(contract, project), contract.name, output, contract
    )
    execution = run_foundry_test(project, generated, experiment.experiment_id, "blind")
    return {
        "generated_path": str(generated),
        "execution": execution,
        "classification": "NOT_REACHED",
        "execution_status": execution.status,
        "execution_executed": execution.executed,
        "tests_run": execution.tests_run,
        "tests_failed": execution.tests_failed,
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
    outcome = classify_initialization_execution(hypothesis, execution)
    return {
        "generated_path": str(generated),
        "execution": execution,
        "classification": outcome.benchmark_status,
        "classification_path": CLASS_CAPABILITIES["initialization"]["classification_path"],
        "internal_status": outcome.internal_status,
        "execution_status": execution.status,
        "execution_executed": execution.executed,
        "tests_run": execution.tests_run,
        "tests_failed": execution.tests_failed,
        "evidence": outcome.evidence,
    }



def _run_guard_parity(project: Path, hypothesis, experiment, contract) -> dict[str, Any]:
    output = test_path_for(project, f"generated/{hypothesis.hypothesis_id}.t.sol")
    generated = generate_guard_parity_test(
        hypothesis, experiment=experiment, contract_model=contract,
        target_import=_target_import(contract, project), target_type=contract.name,
        output_path=output,
    )
    execution = run_foundry_test(project, generated, experiment.experiment_id, "blind")
    return {
        "generated_path": str(generated),
        "execution": execution,
        "classification": "NOT_REACHED",
        "execution_status": execution.status,
        "execution_executed": execution.executed,
        "tests_run": execution.tests_run,
        "tests_failed": execution.tests_failed,
        "classification_blocked_reason": CLASS_CAPABILITIES["guard_parity"]["classify_block_reason"],
    }

def run_layers(result, project: Path, classes: tuple[str, ...], compiler_evidence: CompilerEvidenceResult):
    experiments = {experiment.hypothesis_id: experiment for experiment in result.experiments}
    statuses: list[dict[str, Any]] = []
    executions: list[ExecutionResult] = []
    evidence: list[Any] = []

    for hypothesis in result.hypotheses:
        class_name = INVARIANT_CLASS.get(hypothesis.invariant_id)
        if class_name is None and hypothesis.invariant_id.startswith("INV-STATE-"):
            class_name = "state"
        if class_name is None and hypothesis.invariant_id.startswith("INV-GUARD-PARITY-"):
            class_name = "guard_parity"
        if class_name is None or class_name not in classes:
            continue
        capability = CLASS_CAPABILITIES[class_name]
        experiment = experiments[hypothesis.hypothesis_id]
        contract = _contract_for_hypothesis(result, hypothesis)
        function = next((item for item in contract.functions if item.name == hypothesis.target_function), None)
        readiness = inspect_execution_readiness(
            contract,
            function,
            tuple(item for item in compiler_evidence.constraints if item.contract == contract.name),
            compiler_evidence.evidence,
        )
        prerequisite_graph = build_prerequisite_graph(readiness)
        prerequisite_observation_evidence = ()
        status_prerequisite = {}
        if class_name == "state" and readiness.state_requirements:
            setup_actions = constructible_state_setup_plan(
                contract,
                function,
                tuple(item for item in compiler_evidence.constraints if item.contract == contract.name),
                compiler_evidence.evidence,
            )
            observation_plans = plan_public_state_observations(contract, function)
            if observation_plans:
                try:
                    prerequisite_execution, observations, prerequisite_observation_evidence = _run_state_prerequisite_observation(
                        project, hypothesis, experiment, contract, setup_actions, observation_plans
                    )
                    prerequisite_graph = apply_observations(prerequisite_graph, observations)
                    status_prerequisite = {"prerequisite_setup_actions": [a.function for a in setup_actions], "prerequisite_observations": [o.evidence_id for o in observations], "prerequisite_execution": _json(prerequisite_execution)}
                except Exception as error:
                    status_prerequisite = {"prerequisite_setup_actions": [a.function for a in setup_actions], "prerequisite_observation_failure": f"{type(error).__name__}: {error}"}
            else:
                status_prerequisite = {"prerequisite_observation_failure": "no deterministic public state observation plan"}
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
        relation_execution = None
        relation_evidence = ()

        if not capability["generate_foundry"]:
            status["foundry_generation_blocked_reason"] = capability["generate_block_reason"]
            statuses.append(status)
            continue

        # Do not execute a security experiment until every modeled prerequisite
        # has explicit evidence. Discovery is not verification.
        if not can_enter_security_experiment(prerequisite_graph):
            status["blind_executed"] = False
            status["classification"] = "NOT_REACHED"
            status["classification_blocked_reason"] = "security experiment prerequisites are not verified"
            status["prerequisites"] = _json(prerequisite_graph)
            status.update(status_prerequisite)
            evidence.extend(prerequisite_observation_evidence)
            statuses.append(status)
            continue

        if class_name == "state":
            try:
                relation_execution, relation_plans, relation_evidence = _run_state_relation_verification(
                    project, hypothesis, experiment, contract
                )
                status["state_relation_verification"] = {
                    "verified": bool(relation_evidence),
                    "plans": [
                        {
                            "state": plan.state,
                            "getter": plan.getter,
                            "relation": plan.relation.expression,
                        }
                        for plan in relation_plans
                    ],
                    "execution": _json(relation_execution),
                    "evidence_ids": [item.evidence_id for item in relation_evidence],
                }
                evidence.extend(relation_evidence)
                executions.append(relation_execution)
                if not relation_evidence:
                    # Relation verification is a prerequisite for state security
                    # experiments. Never fall through on a failed or empty assertion.
                    status["blind_executed"] = False
                    status["classification"] = "NOT_REACHED"
                    status["classification_blocked_reason"] = (
                        "state relation verification did not produce passing runtime evidence"
                    )
                    status.update(status_prerequisite)
                    evidence.extend(prerequisite_observation_evidence)
                    statuses.append(status)
                    continue
            except Exception as error:
                status["state_relation_verification"] = {
                    "verified": False,
                    "failure": f"{type(error).__name__}: {error}",
                }
                status["blind_executed"] = False
                status["classification"] = "NOT_REACHED"
                status["classification_blocked_reason"] = (
                    "state relation verification could not be completed"
                )
                status.update(status_prerequisite)
                evidence.extend(prerequisite_observation_evidence)
                statuses.append(status)
                continue

        try:
            if class_name == "authorization":
                run = _run_authorization(project, hypothesis, experiment, contract)
            elif class_name == "state":
                run = _run_state(project, hypothesis, experiment, contract)
            elif class_name == "initialization":
                run = _run_initialization(project, hypothesis, experiment, contract)
            elif class_name == "guard_parity":
                run = _run_guard_parity(project, hypothesis, experiment, contract)
            else:
                raise AssertionError(f"Unhandled supported class: {class_name}")
        except Exception as error:
            stage = "generation" if not any(
                project.joinpath("test").rglob(f"{hypothesis.hypothesis_id}.t.sol")
            ) else "execution"
            statuses.append({**status, **_failure_status(hypothesis, class_name, stage, error)})
            continue

        status.update(status_prerequisite)
        evidence.extend(prerequisite_observation_evidence)
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
        # manifest.sha256 is derived from the other freeze files, so it
        # must be created before checking completeness.
        (freeze / "manifest.sha256").write_text(
            "\n".join(_manifest(freeze)) + "\n", encoding="utf-8"
        )
        missing = [
            name for name in FREEZE_FILES if not (freeze / name).exists()
        ]
        if missing:
            raise RuntimeError(f"Freeze missing files: {missing}")
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
    # Reuse the repository's complete class-neutral planner dispatch. The
    # blind runner only exposes executable layers for the explicitly requested
    # capability classes, but investigation may legitimately generate other
    # hypotheses from compiler/structural evidence. Those hypotheses must not
    # crash the entire blind investigation with a planner KeyError.
    return _default_experiment_planner(hypothesis)

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

        prepare_target_project(project)
        target_intake = inspect_target(project, source)
        if target_intake.adapter == "unsupported":
            raise RuntimeError("target intake could not select a supported execution adapter")
        compiler_evidence: CompilerEvidenceResult = compile_state_effects(project, source)
        surfaces = tuple(
            surface
            for enabled, surface in (
                ("state" in classes, generate_cross_function_state_hypotheses),
                ("arithmetic" in classes, lambda contract, _evidence: ReasoningContribution((), generate_pair_symmetry_hypotheses(contract))),
                ("arithmetic" in classes, lambda contract, _evidence: ReasoningContribution((), generate_aggregation_order_hypotheses(contract))),
                (bool(classes), lambda contract, _evidence: ReasoningContribution((), generate_configuration_binding_hypotheses(contract))),
            )
            if enabled
        )
        result = investigate(
            source,
            target=f"{args.target_repo}@{args.target_ref}",
            semantic_evidence=compiler_evidence.evidence,
            constraint_evidence=compiler_evidence.constraints,
            experiment_planner=_blind_planner,
            reasoning_surfaces=surfaces,
        )
        statuses, executions, evidence = run_layers(result, project, classes, compiler_evidence)
        experiments = {experiment.hypothesis_id: experiment for experiment in result.experiments}
        execution_readiness = []
        for hypothesis in result.hypotheses:
            class_name = INVARIANT_CLASS.get(hypothesis.invariant_id)
            if class_name is None and hypothesis.invariant_id.startswith("INV-STATE-"):
                class_name = "state"
            if class_name is None and hypothesis.invariant_id.startswith("INV-GUARD-PARITY-"):
                class_name = "guard_parity"
            if class_name is None or class_name not in classes:
                continue
            contract = _contract_for_hypothesis(result, hypothesis)
            function = next((item for item in contract.functions if item.name == hypothesis.target_function), None)
            readiness = inspect_execution_readiness(
                contract,
                function,
                tuple(item for item in compiler_evidence.constraints if item.contract == contract.name),
                compiler_evidence.evidence,
            )
            execution_readiness.append({
                "hypothesis_id": hypothesis.hypothesis_id,
                "class": class_name,
                "target_function": hypothesis.target_function,
                "readiness": readiness,
            })
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
            "target-intake.json": target_intake.to_dict(),
            "execution-readiness.json": execution_readiness,
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
