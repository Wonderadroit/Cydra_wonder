from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from dataclasses import asdict, is_dataclass
from pathlib import Path

from cydra.compiler_state import compile_state_effects
from cydra.foundry import run_foundry_test, test_path_for
from cydra.pipeline import investigate, ReasoningContribution
from cydra.planned_foundry import generate_authorization_test_from_experiment
from cydra.reasoning import (
    plan_access_control_experiment,
    plan_initialization_experiment,
)
from cydra.sequence_foundry import generate_sequence_test_from_experiment
from cydra.state_experiments import plan_cross_function_state_experiment
from cydra.structural_state import generate_cross_function_state_hypotheses


TARGET = "https://github.com/alchemix-finance/v3-poc.git"
REF = "a192ab313c81ba3ab621d9ca1ee000110fbdd1e9"
PATH = "src/AlchemistV3.sol"


def jsonable(value):
    if is_dataclass(value):
        return {k: jsonable(v) for k, v in asdict(value).items()}
    if isinstance(value, tuple):
        return [jsonable(v) for v in value]
    if isinstance(value, list):
        return [jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    return value


def state_surface(contract, semantic):
    return generate_cross_function_state_hypotheses(contract, semantic=semantic)


def planner(hypothesis):
    if hypothesis.invariant_id.startswith("INV-STATE-"):
        return plan_cross_function_state_experiment(hypothesis)
    if hypothesis.invariant_id == "INV-AUTH-001":
        return plan_access_control_experiment(hypothesis)
    if hypothesis.invariant_id == "INV-INIT-001":
        return plan_initialization_experiment(hypothesis)
    raise ValueError(f"No generic execution planner for {hypothesis.invariant_id}")


def run_mode(mode: str, root: Path, target: Path, output: Path):
    compiler = compile_state_effects(target.parent, target)
    surfaces = (state_surface,) if mode == "guided-state" else (state_surface,)
    result = investigate(
        target,
        target=f"{TARGET}@{REF}",
        semantic_evidence=compiler.evidence,
        constraint_evidence=compiler.constraints,
        experiment_planner=planner,
        reasoning_surfaces=surfaces,
    )

    rows = []
    with tempfile.TemporaryDirectory(prefix=f"cydra-{mode}-") as temp:
        project = Path(temp)
        # Copy only the target project tree into a disposable Foundry workspace.
        subprocess.run(("cp", "-a", str(target.parent), str(project / "srcroot")), check=True)
        workspace = project / "srcroot"
        for hypothesis in result.hypotheses:
            experiment = next(
                (e for e in result.experiments if e.hypothesis_id == hypothesis.hypothesis_id),
                None,
            )
            if experiment is None:
                continue
            row = {
                "hypothesis_id": hypothesis.hypothesis_id,
                "invariant_id": hypothesis.invariant_id,
                "target_function": hypothesis.target_function,
                "claim": hypothesis.claim,
                "related_functions": hypothesis.related_functions,
                "experiment": jsonable(experiment),
                "mode": mode,
                "execution": None,
            }
            try:
                contract = next(
                    c for c in result.contracts
                    if any(f.name == hypothesis.target_function for f in c.functions)
                )
                relative_source = os.path.relpath(Path(contract.source), workspace).replace(os.sep, "/")
                generated = test_path_for(workspace, f"generated/{hypothesis.hypothesis_id}.t.sol")
                if hypothesis.invariant_id == "INV-STATE-"+hypothesis.target_function:
                    generated = generate_sequence_test_from_experiment(
                        hypothesis, experiment, relative_source, contract.name, generated, contract
                    )
                elif hypothesis.invariant_id == "INV-AUTH-001":
                    generated = generate_authorization_test_from_experiment(
                        hypothesis, experiment, relative_source, contract.name, generated, contract
                    )
                else:
                    row["execution"] = {"status": "not_rendered", "reason": "no generic renderer for this hypothesis"}
                    rows.append(row)
                    continue
                execution = run_foundry_test(
                    workspace, generated, experiment.experiment_id, mode
                )
                row["execution"] = jsonable(execution)
            except Exception as exc:
                row["execution"] = {
                    "status": "error",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            rows.append(row)

    output.mkdir(parents=True, exist_ok=True)
    (output / f"{mode}.json").write_text(
        json.dumps(
            {
                "mode": mode,
                "target": f"{TARGET}@{REF}:{PATH}",
                "compiler_evidence": jsonable(compiler.evidence),
                "hypotheses": jsonable(result.hypotheses),
                "experiments": jsonable(result.experiments),
                "executions": rows,
            },
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("guided-state", "blind"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="cydra-target-") as temp:
        checkout = Path(temp) / "target"
        subprocess.run(("git", "clone", "--no-tags", TARGET, str(checkout)), check=True)
        subprocess.run(("git", "-C", str(checkout), "checkout", "--detach", REF), check=True)
        target = checkout / PATH
        run_mode(args.mode, Path(__file__).resolve().parents[1], target, args.output)


if __name__ == "__main__":
    main()
