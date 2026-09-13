from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
from typing import Any

from .foundry import ExecutionResult
from .models import Evidence, Hypothesis

EXPECTED_TARGETS = ("Minter", "Voter", "Pool")
JSON_COMMAND = ("forge", "test", "--json", "--match-path", "test/cydra_generated/*.t.sol")
HUMAN_COMMAND = ("forge", "test", "--match-path", "test/cydra_generated/*.t.sol")

@dataclass(frozen=True)
class ForgeSummary:
    suites: int
    passed: int
    failed: int
    skipped: int
    total: int

@dataclass(frozen=True)
class InitializationOutcome:
    hypothesis: Hypothesis
    execution: ExecutionResult
    evidence: Evidence
    internal_status: str
    benchmark_status: str

def _strip_ansi(output: str) -> str:
    return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", output)

def parse_forge_human_summary(output: str) -> ForgeSummary:
    clean = _strip_ansi(output)
    suites = re.findall(r"Suite result: (\w+)\. (\d+) passed; (\d+) failed; (\d+) skipped; finished in", clean)
    if not suites:
        raise RuntimeError("human-readable Forge parser failed: no Suite result lines found")
    m = re.search(r"Ran (\d+) test suites? in [^:]+: (\d+) tests? passed, (\d+) failed, (\d+) skipped \((\d+) total tests?\)", clean)
    if m is None:
        raise RuntimeError("human-readable Forge parser failed: aggregate summary line not found")
    summary = ForgeSummary(*(int(value) for value in m.groups()))
    if summary.passed + summary.failed + summary.skipped != summary.total:
        raise RuntimeError(f"human-readable Forge parser failed: aggregate counts do not equal total (passed={summary.passed}, failed={summary.failed}, skipped={summary.skipped}, total={summary.total})")
    if summary.suites != len(suites):
        raise RuntimeError(f"human-readable Forge parser failed: suite count mismatch (aggregate={summary.suites}, suite_lines={len(suites)})")
    suite_failed = sum(int(failed) for _, _, failed, _ in suites)
    if suite_failed != summary.failed:
        raise RuntimeError(f"human-readable Forge parser failed: per-suite failure mismatch (suite_lines={suite_failed}, aggregate={summary.failed})")
    return summary

def parse_forge_json(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Foundry JSON parse failed: {exc}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("Foundry JSON parse failed: top-level value is not an object")
    return parsed

def _json_execution_results(json_output: dict[str, Any], raw_json: str, stderr: str, exit_code: int) -> tuple[ExecutionResult, ...]:
    results: list[ExecutionResult] = []
    seen_targets: set[str] = set()
    for suite_key, suite in json_output.items():
        if ":" not in suite_key:
            continue
        file_path, _contract_name = suite_key.split(":", 1)
        filename = Path(file_path).name
        target = filename.removesuffix(".t.sol")
        if target not in EXPECTED_TARGETS:
            continue
        if target in seen_targets:
            raise RuntimeError(f"duplicate Forge JSON suite for expected target: {target}")
        test_results = suite.get("test_results")
        if not isinstance(test_results, dict):
            raise RuntimeError(f"Forge JSON suite {suite_key} has no test_results object")
        tests_run = len(test_results)
        tests_failed = sum(1 for test in test_results.values() if test.get("status") != "Success")
        results.append(ExecutionResult(f"X-H-INIT-{target}", target, JSON_COMMAND, exit_code, True, tests_run, tests_failed, "PASS" if tests_failed == 0 else "FAIL", raw_json, stderr))
        seen_targets.add(target)
    missing = [target for target in EXPECTED_TARGETS if target not in seen_targets]
    if missing:
        raise RuntimeError(f"Foundry JSON scope mismatch: missing expected targets {missing}")
    return tuple(sorted(results, key=lambda result: EXPECTED_TARGETS.index(result.target)))

def run_initialization_harness(project_dir: str | Path) -> tuple[ExecutionResult, ...]:
    project = Path(project_dir)
    json_completed = subprocess.run(JSON_COMMAND, cwd=project, text=True, capture_output=True, check=False)
    json_output = parse_forge_json(json_completed.stdout)
    results = _json_execution_results(json_output, json_completed.stdout, json_completed.stderr, json_completed.returncode)
    human_completed = subprocess.run(HUMAN_COMMAND, cwd=project, text=True, capture_output=True, check=False)
    human_summary = parse_forge_human_summary(human_completed.stdout + "\n" + human_completed.stderr)
    json_total = sum(result.tests_run for result in results)
    json_failed = sum(result.tests_failed for result in results)
    human_total = human_summary.total
    human_failed = human_summary.failed
    exit_ok = human_completed.returncode == 0
    if json_total != human_total:
        raise RuntimeError(f"integrity assertion 1 failed: total mismatch: JSON {json_total} vs human {human_total}")
    if json_failed != human_failed:
        raise RuntimeError(f"integrity assertion 2 failed: per-suite failures {json_failed} vs aggregate {human_failed}")
    if (json_failed == 0) != exit_ok:
        raise RuntimeError(f"integrity assertion 3 failed: {json_failed} JSON failures vs human exit {human_completed.returncode}")
    return results

def classify_initialization_execution(hypothesis: Hypothesis, execution: ExecutionResult) -> InitializationOutcome:
    """Classify one execution as evidence, never as causal confirmation."""
    evidence_id = f"E-EXEC-{hypothesis.hypothesis_id}-INITIALIZATION"
    evidence = Evidence(evidence_id, "execution", f"Foundry initialization test: status={execution.status}, executed={execution.executed}, tests_run={execution.tests_run}, tests_failed={execution.tests_failed}, exit={execution.exit_code}.", " ".join(execution.command), execution.target + ".t.sol")
    if execution.status == "PASS":
        internal_status, benchmark_status = "rejected", "not_confirmed"
    else:
        internal_status, benchmark_status = "proposed", "proposed"
    updated = Hypothesis(hypothesis.hypothesis_id, hypothesis.claim, hypothesis.invariant_id, hypothesis.target_function, hypothesis.attacker_capability, hypothesis.expected_impact, internal_status, hypothesis.evidence_ids + (evidence_id,))
    return InitializationOutcome(updated, execution, evidence, internal_status, benchmark_status)
