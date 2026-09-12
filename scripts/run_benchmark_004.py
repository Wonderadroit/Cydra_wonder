from __future__ import annotations

import json
from pathlib import Path

from cydra.foundry import (
    ExecutionResult,
    classify_accounting_outcome,
    generate_cached_accounting_foundry_test,
    run_foundry_test,
)
from cydra.models import Evidence
from cydra.pipeline import investigate

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmarks" / "004_yield_live_balance"
FOUNDRY = BENCHMARK / "foundry"
TEST_PATH = FOUNDRY / "test" / "CydraAccountingInvariant.t.sol"
MEASUREMENT_PATH = FOUNDRY / "cydra_accounting_measurements.json"
SOURCE = BENCHMARK / "Target.sol"


def _status_result(status: str, target: str) -> ExecutionResult:
    return ExecutionResult(
        experiment_id="X-H-ACCOUNT-benchmark-control",
        target=target,
        command=("synthetic-control",),
        exit_code=1 if status == "FAIL" else 0,
        executed=True,
        tests_run=1,
        tests_failed=1 if status == "FAIL" else 0,
        status=status,  # type: ignore[arg-type]
        stdout="",
        stderr="",
    )


def main() -> int:
    investigation = investigate(SOURCE, target="benchmark-004-yield-live-balance")
    invariants = [item for item in investigation.invariants if item.invariant_id == "INV-ACCOUNT-001"]
    hypotheses = [item for item in investigation.hypotheses if item.invariant_id == "INV-ACCOUNT-001"]
    experiments = [item for item in investigation.experiments if item.hypothesis_id in {h.hypothesis_id for h in hypotheses}]

    print(json.dumps({
        "boundary": "accounting-execution",
        "invariants": [i.invariant_id for i in invariants],
        "hypotheses": [h.hypothesis_id for h in hypotheses],
        "experiments": [e.experiment_id for e in experiments],
    }, indent=2))

    if len(hypotheses) != 1 or len(experiments) != 1:
        print(json.dumps({"classification": "UNMEASURABLE", "reason": "accounting hypothesis/experiment not produced"}, indent=2))
        return 1

    hypothesis = hypotheses[0]
    experiment = experiments[0]

    if MEASUREMENT_PATH.exists():
        MEASUREMENT_PATH.unlink()

    generated = generate_cached_accounting_foundry_test(
        experiment,
        "../../Target.sol:StrategyVulnerable",
        "../../PatchedTarget.sol:StrategyPatched",
        TEST_PATH,
    )

    source_text = generated.read_text(encoding="utf-8")
    required_runtime_bindings = (
        "vulnerable.poolCached()",
        "pool.balanceOf(address(vulnerable))",
        "vulnerable.burn(holder)",
        "patchedTarget.burn(holder)",
        "vm.writeFile(\"cydra_accounting_measurements.json\"",
        "vm.toString(vulnerablePayout)",
        "vm.toString(patchedPayout)",
    )
    static_plus_execution = all(token in source_text for token in required_runtime_bindings)

    execution = run_foundry_test(
        FOUNDRY,
        TEST_PATH,
        experiment.experiment_id,
        "benchmark-004-vulnerable+patched",
    )

    if execution.status == "UNMEASURABLE":
        print(json.dumps({
            "classification": "UNMEASURABLE",
            "execution": {
                "status": execution.status,
                "tests_run": execution.tests_run,
                "exit_code": execution.exit_code,
                "stdout": execution.stdout,
                "stderr": execution.stderr,
            },
        }, indent=2))
        return 1

    payload = None
    payload_error = None
    if MEASUREMENT_PATH.exists():
        try:
            payload = json.loads(MEASUREMENT_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            payload_error = str(exc)
    else:
        payload_error = "measurement file was not created"

    evidence = Evidence(
        f"E-EXEC-{hypothesis.hypothesis_id}-ACCOUNTING",
        "execution",
        "Accounting measurements transported from executed Solidity through the permitted file channel.",
        "benchmark-004-vulnerable+patched",
        "burn",
        payload if isinstance(payload, dict) else None,
        "static_plus_execution" if static_plus_execution else None,
    )

    if not isinstance(payload, dict) or not static_plus_execution:
        classification = "FALSIFIED"
        reason = payload_error or "runtime source binding was not preserved"
    else:
        outcome = classify_accounting_outcome(hypothesis, evidence, execution, execution)
        classification = outcome.hypothesis.status.upper()
        reason = "accounting numerical differential"

    negative_payload = {
        "vulnerableCachedBefore": 200,
        "patchedCachedBefore": 200,
        "vulnerableLiveAfterDonation": 200,
        "patchedLiveAfterDonation": 200,
        "referencePayout": 100,
        "vulnerablePayout": 100,
        "patchedPayout": 100,
        "donation": 0,
    }
    negative_evidence = Evidence(
        "E-NEGATIVE-ACCOUNTING",
        "execution",
        "Accounting negative control with no donation-induced numerical differential.",
        "benchmark-004-negative-control",
        "burn",
        negative_payload,
        "static_plus_execution",
    )
    negative_outcome = classify_accounting_outcome(
        hypothesis,
        negative_evidence,
        _status_result("FAIL", "negative-vulnerable"),
        _status_result("PASS", "negative-patched"),
    )

    legacy_outcome = classify_accounting_outcome(
        hypothesis,
        Evidence("E-LEGACY", "execution", "Legacy status control.", "legacy-control", "burn", None, None),
        _status_result("FAIL", "legacy-vulnerable"),
        _status_result("PASS", "legacy-patched"),
    )

    print(json.dumps({
        "classification": classification,
        "reason": reason,
        "execution": {
            "status": execution.status,
            "executed": execution.executed,
            "tests_run": execution.tests_run,
            "tests_failed": execution.tests_failed,
            "exit_code": execution.exit_code,
        },
        "evidence": {
            "payload_present": isinstance(payload, dict),
            "source_verification": evidence.source_verification,
            "payload": payload,
        },
        "negative_control": {
            "status_pattern": "FAIL/PASS",
            "numerical_differential": False,
            "classification": negative_outcome.hypothesis.status,
        },
        "legacy_control": {
            "status_pattern": "FAIL/PASS",
            "payload": None,
            "classification": legacy_outcome.hypothesis.status,
        },
    }, indent=2))

    return 0 if classification == "CONFIRMED" and negative_outcome.hypothesis.status == "proposed" and legacy_outcome.hypothesis.status == "confirmed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
