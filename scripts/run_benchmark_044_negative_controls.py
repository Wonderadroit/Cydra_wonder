from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from cydra.foundry import (
    generate_access_control_test,
    generate_initialization_test,
    require_executed,
    run_foundry_test,
    test_path_for,
)
from cydra.pipeline import investigate
from cydra.reasoning import plan_temporal_precondition_experiment
from cydra.structural_temporal import generate_temporal_precondition_hypotheses
from cydra.temporal_precondition_execution import generate_temporal_precondition_test
from cydra.solidity_model import parse_solidity

ROOT = Path(__file__).resolve().parents[1]


def _project(source: Path, root: Path) -> Path:
    (root / "src").mkdir(parents=True)
    (root / "test").mkdir(parents=True)
    (root / "foundry.toml").write_text(
        "[profile.default]\nsrc='src'\ntest='test'\nlibs=[]\n",
        encoding="utf-8",
    )
    subprocess.run(("git", "init"), cwd=root, check=True, capture_output=True)
    subprocess.run(("forge", "install", "foundry-rs/forge-std", "--no-commit"), cwd=root, check=True)
    destination = root / "src" / source.name
    shutil.copy2(source, destination)
    return destination


def _run_auth(root: Path) -> dict:
    source = ROOT / "benchmarks/alchemix_missing_access_control/SafeTarget.sol"
    result = investigate(source)
    hypotheses = [h for h in result.hypotheses if h.invariant_id == "INV-AUTH-001"]
    if len(hypotheses) != 1:
        raise AssertionError(f"authorization negative control expected one hypothesis, got {len(hypotheses)}")
    hypothesis = hypotheses[0]
    target = _project(source, root)
    generated = generate_access_control_test(
        hypothesis,
        f"../../src/{target.name}",
        "AlchemixAccessControlSafeFixture",
        test_path_for(root, f"generated/{hypothesis.hypothesis_id}.t.sol"),
    )
    execution = run_foundry_test(root, generated, f"X-{hypothesis.hypothesis_id}-NEGATIVE", "authorization-safe")
    require_executed(execution)
    return {
        "control": "authorization-safe",
        "hypothesis_id": hypothesis.hypothesis_id,
        "execution_status": execution.status,
        "executed": execution.executed,
        "tests_run": execution.tests_run,
        "tests_failed": execution.tests_failed,
    }


def _run_init(root: Path) -> dict:
    source = ROOT / "benchmarks/wormhole_uninitialized/SafeTarget.sol"
    result = investigate(source)
    hypotheses = [h for h in result.hypotheses if h.invariant_id == "INV-INIT-001"]
    if len(hypotheses) != 1:
        raise AssertionError(f"initialization negative control expected one hypothesis, got {len(hypotheses)}")
    hypothesis = hypotheses[0]
    target = _project(source, root)
    generated = generate_initialization_test(
        hypothesis,
        f"../../src/{target.name}",
        "WormholeInitializationFixture",
        test_path_for(root, f"generated/{hypothesis.hypothesis_id}.t.sol"),
    )
    execution = run_foundry_test(root, generated, f"X-{hypothesis.hypothesis_id}-NEGATIVE", "initialization-safe")
    require_executed(execution)
    return {
        "control": "initialization-safe",
        "hypothesis_id": hypothesis.hypothesis_id,
        "execution_status": execution.status,
        "executed": execution.executed,
        "tests_run": execution.tests_run,
        "tests_failed": execution.tests_failed,
    }


def _run_temporal(root: Path) -> dict:
    source = ROOT / "benchmarks/010_temporal_precondition/TemporalPreconditionTargetPatched.sol"
    result = investigate(
        source,
        reasoning_surfaces=(generate_temporal_precondition_hypotheses,),
        experiment_planner=plan_temporal_precondition_experiment,
    )
    hypotheses = [h for h in result.hypotheses if h.invariant_id.startswith("INV-TEMPORAL-PRECONDITION-")]
    if len(hypotheses) != 1:
        raise AssertionError(f"temporal negative control expected one hypothesis, got {len(hypotheses)}")
    hypothesis = hypotheses[0]
    experiment = next(e for e in result.experiments if e.hypothesis_id == hypothesis.hypothesis_id)
    target = _project(source, root)
    contract = parse_solidity(target)[0]
    generated = generate_temporal_precondition_test(
        hypothesis,
        contract,
        f"../../src/{target.name}",
        contract.name,
        test_path_for(root, f"generated/{hypothesis.hypothesis_id}.t.sol"),
        experiment=experiment,
    )
    execution = run_foundry_test(root, generated, experiment.experiment_id, "temporal-safe")
    require_executed(execution)
    return {
        "control": "temporal-safe",
        "hypothesis_id": hypothesis.hypothesis_id,
        "execution_status": execution.status,
        "executed": execution.executed,
        "tests_run": execution.tests_run,
        "tests_failed": execution.tests_failed,
    }


def main() -> int:
    controls = []
    with tempfile.TemporaryDirectory(prefix="cydra-044-") as temp:
        root = Path(temp)
        for runner in (_run_auth, _run_init, _run_temporal):
            controls.append(runner(root / runner.__name__))

    failures = [c for c in controls if c["execution_status"] != "PASS" or not c["executed"] or c["tests_failed"]]
    result = {
        "benchmark": "044-negative-control-campaign",
        "controls_total": len(controls),
        "controls_passed": len(controls) - len(failures),
        "controls_failed": len(failures),
        "false_positive_gate": "READY" if not failures else "BLOCKED",
        "controls": controls,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
