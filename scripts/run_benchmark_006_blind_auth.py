from __future__ import annotations

import argparse
import json
from pathlib import Path
import os
import subprocess
import tempfile
import re
import shutil

from cydra.authorization_runtime import classify_authorization_blind_execution
from cydra.blind_authorization import generate_blind_authorization_test_from_experiment
from cydra.compiler_state import compile_state_effects
from cydra.foundry import ExecutionResult, require_executed, run_foundry_test, test_path_for
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
        try:
            relative = current.relative_to(source_root)
            destination_file = src_root / relative
        except ValueError:
            relative = current.relative_to(target_root)
            destination_file = destination / "src" / relative
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

    remapping_lines = []
    for prefix, destination_path in remappings:
        # Remapped dependencies under node_modules live at the Foundry root;
        # source-tree dependencies copied by the closure live under src/.
        remapped_root = "node_modules" if destination_path.startswith("node_modules/") else "src"
        remapping_lines.append(f"{prefix}={remapped_root}/{destination_path}")
    remapping_literal = ", ".join(repr(item) for item in remapping_lines)
    (destination / "foundry.toml").write_text(
        '[profile.default]\n'
        'src = "src"\n'
        'test = "test"\n'
        'libs = ["lib"]\n'
        'auto_detect_solc = true\n'
        f"remappings = [{remapping_literal}]\n",
        encoding="utf-8",
    )
    hardhat_console = destination / "lib" / "hardhat" / "console.sol"
    hardhat_console.parent.mkdir(parents=True, exist_ok=True)
    hardhat_console.write_text("pragma solidity ^0.6.12; library console {}\n", encoding="utf-8")
    (destination / "remappings.txt").write_text(
        "\n".join(remapping_lines) + "\n",
        encoding="utf-8",
    )
    return test_root


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ("git", *args), cwd=cwd, text=True, capture_output=True, check=True
    ).stdout.strip()


def _auth_modifier(source):
    defs = {}
    for m in re.finditer(r"\bmodifier\s+(\w+)\s*\([^)]*\)\s*\{", source):
        body=source[m.end():]; depth=1
        for i,ch in enumerate(body):
            if ch=="{": depth+=1
            elif ch=="}":
                depth-=1
                if depth==0:
                    defs[m.group(1)]=body[:i]; break
    counts={}
    for m in re.finditer(r"\bfunction\s+\w+\s*\([^)]*\)([^{};]*)\{", source):
        for tok in re.findall(r"\b[A-Za-z_]\w*\b",m.group(1)):
            b=defs.get(tok)
            if b and re.search(r"\b(?:msg\.sender|_msgSender\(\)|tx\.origin)\b",b) and re.search(r"\b(?:require|revert|assert)\b",b):
                counts[tok]=counts.get(tok,0)+1
    return max(counts,key=counts.get) if counts else None

def _apply_auth_control(source, function_name, modifier):
    original=source.read_text(encoding="utf-8")
    pat=re.compile(rf"(\bfunction\s+{re.escape(function_name)}\s*\([^)]*\))([^{{;]*)(\{{)",re.MULTILINE)
    m=pat.search(original)
    if not m: raise RuntimeError(f"cannot patch {function_name}")
    tail=m.group(2)
    if re.search(rf"\b{re.escape(modifier)}\b",tail): raise RuntimeError("target already has inferred modifier")
    source.write_text(original[:m.start(2)]+tail+" "+modifier+" "+original[m.end(2):],encoding="utf-8")
    return original

def _patched_auth_test(generated,destination):
    s=generated.read_text(encoding="utf-8")
    patched, count = re.subn(
        r'require\(ok,\s*"[^"]*"\);',
        "if (!ok) return;",
        s,
        count=1,
    )
    if count == 0:
        patched, count = re.subn(
            r'require\(\s*!ok,\s*"[^"]*"\s*\);',
            "if (!ok) return;",
            s,
            count=1,
        )
    if count != 1:
        raise RuntimeError("authorization assertion marker missing")
    destination.write_text(patched,encoding="utf-8")

def _json(v):
    if hasattr(v,"__dict__"): return {k:_json(x) for k,x in v.__dict__.items()}
    if isinstance(v,(tuple,list)): return [_json(x) for x in v]
    if isinstance(v,dict): return {str(k):_json(x) for k,x in v.items()}
    return v

def main() -> int:
    parser = argparse.ArgumentParser(description="Blind one-sided authorization backtest.")
    parser.add_argument("--target-repo", required=True)
    parser.add_argument("--target-ref", required=True)
    parser.add_argument("--target-path", required=True)
    parser.add_argument("--target-project", required=True)
    parser.add_argument("--expected-status", choices=("confirmed", "not_confirmed"), default="confirmed")
    parser.add_argument("--require-ready", action="store_true")
    parser.add_argument("--output", type=Path)
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
                # Foundry does not search npm's node_modules tree by default.
                # Historical Alchemix imports use the package prefix directly,
                # so add the deterministic remapping in the isolated project.
                foundry_toml = execution_project / "foundry.toml"
                remapping = "@openzeppelin/=node_modules/@openzeppelin/"
                current = foundry_toml.read_text(encoding="utf-8")
                current = current.replace(
                    'remappings = [',
                    'remappings = [' + repr(remapping) + ', ',
                    1,
                )
                foundry_toml.write_text(current, encoding="utf-8")

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
            # The blind harness now deploys the modeled contract directly.
            # Avoid a separate forge-inspect preflight: Foundry's generated
            # constructor helper can fail before the actual experiment even
            # when the typed deployment is valid. Execution itself remains the
            # authoritative compilation/execution measurement.
            creation_bytecode = None
            output = test_path_for(execution_project, f"generated/{hypothesis.hypothesis_id}.t.sol")
            try:
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
                )
            except ValueError as exc:
                # A missing constructor type is a modeling/execution-precondition
                # gap, not evidence about the target. Preserve it explicitly as
                # UNMEASURABLE instead of fabricating an ABI value or crashing the
                # benchmark before an evidence artifact can be written.
                execution = ExecutionResult(
                    experiment_id=experiment.experiment_id,
                    target=str(source),
                    command=("cydra", "render_authorization_test"),
                    exit_code=2,
                    executed=False,
                    tests_run=0,
                    tests_failed=0,
                    status="UNMEASURABLE",
                    stdout="",
                    stderr=f"authorization experiment could not be rendered faithfully: {exc}",
                )
                print("EXECUTION_STATUS", execution.status, "reason=", execution.stderr)
                outcome = classify_authorization_blind_execution(hypothesis, execution)
                payload = {
                    "target": f"{args.target_repo}@{args.target_ref}:{args.target_path}",
                    "hypothesis": _json(hypothesis),
                    "experiment": _json(experiment),
                    "blind_execution": _json(execution),
                    "classification": outcome.benchmark_status,
                    "finding_gate": "NOT_READY",
                }
                if args.output:
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    args.output.write_text(
                        json.dumps(_json(payload), indent=2) + "\\n",
                        encoding="utf-8",
                    )
                print(
                    f"{hypothesis.hypothesis_id}: status={execution.status} "
                    f"classification={outcome.benchmark_status} evidence={outcome.evidence.evidence_id}"
                )
                return 2
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
            payload={"target":f"{args.target_repo}@{args.target_ref}:{args.target_path}","hypothesis":_json(hypothesis),"experiment":_json(experiment),"blind_execution":_json(execution),"classification":outcome.benchmark_status,"finding_gate":"CONFIRMED_ONLY"}
            if args.require_ready and outcome.benchmark_status=="confirmed":
                isolated_source = execution_project / "src" / source_relative
                modifier=_auth_modifier(isolated_source.read_text(encoding="utf-8"))
                if modifier is None: print("AUTHORIZATION_CAUSAL_CONTROL_UNAVAILABLE"); return 3
                original=_apply_auth_control(isolated_source,hypothesis.target_function,modifier)
                try:
                    patched_test=generated.with_name(generated.stem+"-patched.t.sol"); _patched_auth_test(generated,patched_test)
                    patched=run_foundry_test(execution_project,patched_test,hypothesis.hypothesis_id+":patched","patched")
                finally: isolated_source.write_text(original,encoding="utf-8")
                causal=execution.status=="FAIL" and patched.status=="PASS"
                reproduction=run_foundry_test(execution_project,generated,hypothesis.hypothesis_id+":reproduction","reproduction")
                original=_apply_auth_control(isolated_source,hypothesis.target_function,modifier)
                try:
                    repro_test=generated.with_name(generated.stem+"-reproduction-patched.t.sol"); _patched_auth_test(generated,repro_test)
                    repro_patched=run_foundry_test(execution_project,repro_test,hypothesis.hypothesis_id+":reproduction-patched","reproduction-patched")
                finally: isolated_source.write_text(original,encoding="utf-8")
                repro= reproduction.status=="FAIL" and repro_patched.status=="PASS"
                payload.update({"authorization_control":modifier,"patched_execution":_json(patched),"causal_verification":{"state":"verified" if causal else "not_verified","chain_id":"causal:authorization-modifier-differential"},"reproduction_execution":_json(reproduction),"reproduction_patched_execution":_json(repro_patched),"reproduction_verification":{"state":"verified" if repro else "not_verified","chain_id":"reproduction:authorization-modifier-differential"},"finding_gate":"READY" if causal and repro else "NOT_READY"})
                if not (causal and repro): return 4
            if args.output:
                args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(_json(payload),indent=2)+"\n",encoding="utf-8")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
