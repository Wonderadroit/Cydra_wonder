from __future__ import annotations

import argparse
from pathlib import Path
import os
import subprocess
import tempfile
import re
import shutil

from cydra.authorization_runtime import classify_authorization_blind_execution
from cydra.blind_authorization import generate_blind_authorization_test_from_experiment
from cydra.compiler_state import compile_state_effects
from cydra.foundry import require_executed, run_foundry_test, test_path_for
from cydra.pipeline import investigate
from cydra.reasoning import plan_access_control_experiment

_IMPORT_RE = re.compile(r'''\bimport\s+(?:[^\"']+\s+from\s+)?[\"']([^\"']+)[\"']\s*;''')


def _prepare_isolated_foundry_project(target_root: Path, source: Path, destination: Path) -> Path:
    """Copy only the target's local Solidity import closure into a clean Foundry root."""
    source_root = next(
        (
            candidate
            for candidate in (source.parents)
            if candidate.name in {"src", "contracts"}
        ),
        target_root,
    )
    src_root = destination / "src"
    src_root.mkdir(parents=True, exist_ok=True)
    test_root = destination / "test" / "generated"
    test_root.mkdir(parents=True, exist_ok=True)

    pending = [source]
    copied: set[Path] = set()
    while pending:
        current = pending.pop()
        relative = current.relative_to(source_root)
        destination_file = src_root / relative
        if current in copied:
            continue
        copied.add(current)
        destination_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(current, destination_file)

        text = current.read_text(encoding="utf-8")
        remappings = []
        remappings_file = target_root / "remappings.txt"
        if remappings_file.exists():
            for line in remappings_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                prefix, destination_path = line.split("=", 1)
                remappings.append((prefix, destination_path))
        for imported in _IMPORT_RE.findall(text):
            if imported.startswith("."):
                dependency = (current.parent / imported).resolve()
            elif imported.startswith("contracts/"):
                dependency = (target_root / imported).resolve()
            else:
                dependency = None
                for prefix, destination_path in sorted(remappings, key=lambda item: len(item[0]), reverse=True):
                    if imported.startswith(prefix):
                        suffix = imported[len(prefix):]
                        dependency = (target_root / destination_path / suffix).resolve()
                        break
                if dependency is None:
                    continue
            if dependency.is_file() and dependency not in copied:
                pending.append(dependency)

    (destination / "foundry.toml").write_text(
        '[profile.default]\n'
        'src = "src"\n'
        'test = "test"\n'
        'libs = ["lib"]\n'
        'auto_detect_solc = true\n'
        'remappings = ["@openzeppelin/contracts/=node_modules/@openzeppelin/contracts/"]\n',
        encoding="utf-8",
    )
    hardhat_console = destination / "lib" / "hardhat" / "console.sol"
    hardhat_console.parent.mkdir(parents=True, exist_ok=True)
    hardhat_console.write_text("pragma solidity ^0.6.12; library console {}\n", encoding="utf-8")
    (destination / "remappings.txt").write_text(
        "@openzeppelin/contracts/=node_modules/@openzeppelin/contracts/\n",
        encoding="utf-8",
    )
    return test_root


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ("git", *args), cwd=cwd, text=True, capture_output=True, check=True
    ).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Blind one-sided authorization backtest.")
    parser.add_argument("--target-repo", required=True)
    parser.add_argument("--target-ref", required=True)
    parser.add_argument("--target-path", required=True)
    parser.add_argument("--target-project", required=True)
    parser.add_argument("--expected-status", choices=("confirmed", "not_confirmed"), default="confirmed")
    parser.add_argument(
        "--supplemental-file",
        action="append",
        default=[],
        help="Copy a target-relative file from another git ref using path@ref, for historical build repairs.",
    )
    parser.add_argument(
        "--target-npm-dependency",
        action="append",
        default=[],
        help="Install an npm package into the historical target before bounded execution.",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="cydra-blind-auth-") as temp:
        checkout = Path(temp) / "target"
        subprocess.run(("git", "clone", "--no-tags", "--recurse-submodules", args.target_repo, str(checkout)), check=True)
        subprocess.run(("git", "-C", str(checkout), "fetch", "--no-tags", "origin", args.target_ref), check=True)
        subprocess.run(("git", "-C", str(checkout), "checkout", "--detach", args.target_ref), check=True)
        project = checkout / args.target_project
        source = checkout / args.target_path
        for supplemental in args.supplemental_file:
            try:
                relative_path, supplemental_ref = supplemental.rsplit("@", 1)
            except ValueError as exc:
                raise SystemExit(f"Invalid supplemental file {supplemental!r}; expected path@ref") from exc
            blob = subprocess.run(
                ("git", "-C", str(checkout), "show", f"{supplemental_ref}:{relative_path}"),
                text=True,
                capture_output=True,
                check=True,
            ).stdout
            destination = checkout / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(blob, encoding="utf-8")
        compiler = compile_state_effects(project, source)
        result = investigate(
            source,
            target=f"{args.target_repo}@{args.target_ref}",
            semantic_evidence=compiler.evidence,
            constraint_evidence=compiler.constraints,
            experiment_planner=plan_access_control_experiment,
        )
        hypotheses = [h for h in result.hypotheses if h.invariant_id == "INV-AUTH-001"]
        if not hypotheses:
            print("NO_AUTH_HYPOTHESIS")
            for contract in result.contracts:
                print("CONTRACT", contract.name, "functions=", len(contract.functions))
                for function in contract.functions:
                    print("FUNCTION", function.name, "visibility=", function.visibility, "modifiers=", function.modifiers, "writes=", function.writes)
            print("INVARIANTS", [item.__dict__ for item in result.invariants])
            raise SystemExit("blind authorization backtest produced no authorization hypothesis")

        for dependency in args.target_npm_dependency:
            subprocess.run(
                ("npm", "install", dependency, "--no-save", "--ignore-scripts", "--no-audit", "--no-fund"),
                cwd=project,
                check=True,
            )

        execution_project = Path(temp) / "execution-project"
        _prepare_isolated_foundry_project(checkout, source, execution_project)
        for dependency in args.target_npm_dependency:
            package_name = dependency.split("@", 1)[0] if not dependency.startswith("@") else dependency.rsplit("@", 1)[0]
            if package_name == "@openzeppelin/contracts":
                package_source = project / "node_modules" / "@openzeppelin" / "contracts"
                package_destination = execution_project / "node_modules" / "@openzeppelin" / "contracts"
                package_destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(package_source, package_destination, dirs_exist_ok=True)

        source_root = next(
            (
                candidate
                for candidate in source.parents
                if candidate.name in {"src", "contracts"}
            ),
            project,
        )
        source_relative = Path(source).relative_to(source_root)
        for hypothesis in hypotheses:
            experiment = next(e for e in result.experiments if e.hypothesis_id == hypothesis.hypothesis_id)
            contract = next(
                c for c in result.contracts
                if any(f.name == hypothesis.target_function for f in c.functions)
            )
            contract_identifier = f"src/{source_relative}:{contract.name}"
            bytecode_result = subprocess.run(
                ("forge", "inspect", contract_identifier, "bytecode"),
                cwd=execution_project,
                text=True,
                capture_output=True,
                check=True,
            )
            creation_bytecode = bytecode_result.stdout.strip().removeprefix("0x")
            output = test_path_for(execution_project, f"generated/{hypothesis.hypothesis_id}.t.sol")
            generated = generate_blind_authorization_test_from_experiment(
                hypothesis,
                experiment,
                os.path.relpath(
                    execution_project / "src" / Path(contract.source).relative_to(source_root),
                    output.parent,
                ).replace(os.sep, "/"),
                contract.name,
                output,
                contract,
                creation_bytecode=creation_bytecode,
            )
            execution = run_foundry_test(execution_project, generated, experiment.experiment_id, "blind")
            print("EXECUTION_STATUS", execution.status, "exit=", execution.exit_code, "tests=", execution.tests_run, "failed=", execution.tests_failed)
            print(execution.stdout)
            print(execution.stderr)
            require_executed(execution)
            outcome = classify_authorization_blind_execution(hypothesis, execution)
            print(
                f"{hypothesis.hypothesis_id}: status={execution.status} "
                f"classification={outcome.benchmark_status} evidence={outcome.evidence.evidence_id}"
            )
            if outcome.benchmark_status != args.expected_status:
                return 2
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
