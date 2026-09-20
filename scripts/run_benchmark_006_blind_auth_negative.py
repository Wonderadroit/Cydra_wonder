from __future__ import annotations

from pathlib import Path
import os
import shutil
import subprocess
import tempfile

from cydra.authorization_runtime import classify_authorization_blind_execution
from cydra.blind_authorization import generate_blind_authorization_test_from_experiment
from cydra.compiler_state import compile_state_effects
from cydra.foundry import require_executed, run_foundry_test, test_path_for
from cydra.pipeline import investigate
from cydra.reasoning import plan_access_control_experiment


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="cydra-blind-auth-negative-") as temp:
        checkout = Path(temp) / "target"
        subprocess.run(
            ("git", "clone", "--no-tags", "https://github.com/Wonderadroit/Cydra_wonder.git", str(checkout)),
            check=True,
        )
        subprocess.run(("git", "-C", str(checkout), "checkout", "--detach", "main"), check=True)
        project = checkout / "benchmarks/alchemix_missing_access_control/foundry"
        source = checkout / "benchmarks/alchemix_missing_access_control/SafeTarget.sol"
        subprocess.run(("forge", "install", "foundry-rs/forge-std", "--no-commit"), cwd=project, check=True)

        target_source = project / "src/SafeTarget.sol"
        shutil.copy2(source, target_source)
        compiler = compile_state_effects(project, target_source)
        result = investigate(
            target_source,
            target="benchmark-006-safe-authorization-negative-control",
            semantic_evidence=compiler.evidence,
            constraint_evidence=compiler.constraints,
            experiment_planner=plan_access_control_experiment,
        )
        hypotheses = [h for h in result.hypotheses if h.invariant_id == "INV-AUTH-001"]
        if len(hypotheses) != 1:
            raise SystemExit(f"expected one authorization hypothesis, got {len(hypotheses)}")

        hypothesis = hypotheses[0]
        experiment = next(e for e in result.experiments if e.hypothesis_id == hypothesis.hypothesis_id)
        contract = next(c for c in result.contracts if any(f.name == hypothesis.target_function for f in c.functions))
        output = test_path_for(project, f"generated/{hypothesis.hypothesis_id}.t.sol")
        bytecode = subprocess.run(
            ("forge", "inspect", f"src/SafeTarget.sol:{contract.name}", "bytecode"),
            cwd=project,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip().removeprefix("0x")
        generated = generate_blind_authorization_test_from_experiment(
            hypothesis,
            experiment,
            os.path.relpath(Path(contract.source), output.parent).replace(os.sep, "/"),
            contract.name,
            output,
            contract,
            creation_bytecode=bytecode,
        )
        execution = run_foundry_test(project, generated, experiment.experiment_id, "blind-negative")
        require_executed(execution)
        outcome = classify_authorization_blind_execution(hypothesis, execution)
        print(
            f"{hypothesis.hypothesis_id}: status={execution.status} "
            f"classification={outcome.benchmark_status} evidence={outcome.evidence.evidence_id}"
        )
        return 0 if outcome.benchmark_status == "not_confirmed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
