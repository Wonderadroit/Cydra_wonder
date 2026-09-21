from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from cydra.foundry import run_foundry_test
from cydra.hypothesis_selection import select_next_hypothesis
from cydra.pipeline import investigate
from cydra.research_loop import run_research_loop
from cydra.solidity_model import parse_solidity
from cydra.structural_auth_execution import generate_structural_authorization_test

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "benchmarks/038_multi_finding_blind/Target.sol"
PATCHED = ROOT / "benchmarks/038_multi_finding_blind/PatchedTarget.sol"


@dataclass(frozen=True)
class Observation:
    status: str
    hypothesis_id: str
    target_function: str
    vulnerable: object
    patched: object


@dataclass(frozen=True)
class Finding:
    finding_id: str
    hypothesis_id: str


def setup(dest: Path) -> Path:
    subprocess.run(
        ("forge", "init", "--force", str(dest)),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    subprocess.run(
        ("forge", "install", "foundry-rs/forge-std", "--no-commit"),
        cwd=dest,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    (dest / "Target.sol").write_text(TARGET.read_text(encoding="utf-8"), encoding="utf-8")
    (dest / "PatchedTarget.sol").write_text(PATCHED.read_text(encoding="utf-8"), encoding="utf-8")
    return dest


def execute_hypothesis(root: Path, hypothesis, model) -> Observation:
    vulnerable_test = root / "test" / f"auth_{hypothesis.target_function}_vulnerable.t.sol"
    patched_test = root / "test" / f"auth_{hypothesis.target_function}_patched.t.sol"
    generate_structural_authorization_test(
        hypothesis, model, "../Target.sol", model.name, vulnerable_test
    )
    generate_structural_authorization_test(
        hypothesis, model, "../PatchedTarget.sol", model.name, patched_test
    )
    vulnerable = run_foundry_test(
        root, vulnerable_test, f"X-038-{hypothesis.target_function}-vulnerable", "vulnerable"
    )
    patched = run_foundry_test(
        root, patched_test, f"X-038-{hypothesis.target_function}-patched", "patched"
    )
    status = "confirmed" if (
        vulnerable.executed and patched.executed
        and vulnerable.status == "PASS"
        and patched.status == "FAIL"
    ) else "proposed"
    return Observation(status, hypothesis.hypothesis_id, hypothesis.target_function, vulnerable, patched)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("backtest-artifacts/benchmark-038"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    investigation = investigate(TARGET, target="benchmark-038-multi-finding")
    model = parse_solidity(TARGET)[0]
    if len(investigation.hypotheses) < 2:
        raise SystemExit("multi-finding target did not produce at least two blind hypotheses")

    with tempfile.TemporaryDirectory(prefix="cydra-038-") as tmp:
        root = setup(Path(tmp) / "project")
        experiments = investigation.experiments

        def execute(hypothesis, _experiment):
            return execute_hypothesis(root, hypothesis, model)

        def finding_of(observation):
            if observation.status != "confirmed":
                return None
            return Finding(
                finding_id=f"F-038-{observation.target_function}",
                hypothesis_id=observation.hypothesis_id,
            )

        result = run_research_loop(
            investigation.hypotheses,
            investigation.invariants,
            experiments,
            execute=execute,
            status_of=lambda observation: observation.status,
            finding_of=finding_of,
            finding_target="benchmark-038-multi-finding",
            max_rounds=2,
        )

        payload = {
            "benchmark": "038",
            "strict_blind": True,
            "hypotheses": [h.hypothesis_id for h in investigation.hypotheses],
            "rounds": [
                {
                    "hypothesis": r.selection.hypothesis.hypothesis_id,
                    "target_function": r.observation.target_function,
                    "status": r.status,
                    "vulnerable": {
                        "status": r.observation.vulnerable.status,
                        "executed": r.observation.vulnerable.executed,
                        "tests_run": r.observation.vulnerable.tests_run,
                        "tests_failed": r.observation.vulnerable.tests_failed,
                    },
                    "patched": {
                        "status": r.observation.patched.status,
                        "executed": r.observation.patched.executed,
                        "tests_run": r.observation.patched.tests_run,
                        "tests_failed": r.observation.patched.tests_failed,
                    },
                }
                for r in result.rounds
            ],
            "finding_ids": [f.finding_id for f in result.findings.findings] if result.findings else [],
        }
        (args.output / "result.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(json.dumps(payload, indent=2))

        if len(result.rounds) != 2:
            raise SystemExit("research loop did not continue after the first confirmed finding")
        if result.findings is None or len(result.findings.findings) != 2:
            raise SystemExit("research loop did not accumulate two independently confirmed findings")
        if any(round_.status != "confirmed" for round_ in result.rounds):
            raise SystemExit("one or more multi-finding rounds did not reach confirmed status")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
