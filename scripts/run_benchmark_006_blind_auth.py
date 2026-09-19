from __future__ import annotations

import argparse
from pathlib import Path
import os
import subprocess
import tempfile

from cydra.authorization_runtime import classify_authorization_blind_execution
from cydra.blind_authorization import generate_blind_authorization_test_from_experiment
from cydra.compiler_state import compile_state_effects
from cydra.foundry import require_executed, run_foundry_test, test_path_for
from cydra.pipeline import investigate
from cydra.reasoning import plan_access_control_experiment


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
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="cydra-blind-auth-") as temp:
        checkout = Path(temp) / "target"
        subprocess.run(("git", "clone", "--no-tags", args.target_repo, str(checkout)), check=True)
        subprocess.run(("git", "-C", str(checkout), "checkout", "--detach", args.target_ref), check=True)
        project = checkout / args.target_project
        source = checkout / args.target_path
        subprocess.run(("forge", "install", "foundry-rs/forge-std", "--no-commit"), cwd=project, check=True)

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
            raise SystemExit("blind authorization backtest produced no authorization hypothesis")

        for hypothesis in hypotheses:
            experiment = next(e for e in result.experiments if e.hypothesis_id == hypothesis.hypothesis_id)
            contract = next(
                c for c in result.contracts
                if any(f.name == hypothesis.target_function for f in c.functions)
            )
            output = test_path_for(project, f"generated/{hypothesis.hypothesis_id}.t.sol")
            generated = generate_blind_authorization_test_from_experiment(
                hypothesis,
                experiment,
                os.path.relpath(Path(contract.source), output.parent).replace(os.sep, "/"),
                contract.name,
                output,
                contract,
            )
            print(generated.read_text(encoding="utf-8"))
            execution = run_foundry_test(project, generated, experiment.experiment_id, "blind")
            print("EXECUTION_STATUS", execution.status, "exit=", execution.exit_code, "tests=", execution.tests_run, "failed=", execution.tests_failed)
            print(execution.stdout)
            print(execution.stderr)
            require_executed(execution)
            outcome = classify_authorization_blind_execution(hypothesis, execution)
            print(
                f"{hypothesis.hypothesis_id}: status={execution.status} "
                f"classification={outcome.benchmark_status} evidence={outcome.evidence.evidence_id}"
            )
            if outcome.benchmark_status != "confirmed":
                return 2
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
