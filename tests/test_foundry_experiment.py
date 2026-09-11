from pathlib import Path

import pytest

from cydra.foundry import (
    ExecutionResult,
    classify_access_control_outcome,
    generate_access_control_test,
    require_executed,
)
from cydra.pipeline import investigate


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "benchmarks" / "alchemix_missing_access_control" / "Target.sol"


def _execution(experiment_id: str, target: str, exit_code: int, status: str, tests_run: int, tests_failed: int) -> ExecutionResult:
    return ExecutionResult(
        experiment_id,
        target,
        ("forge", "test"),
        exit_code,
        tests_run > 0,
        tests_run,
        tests_failed,
        status,
        "output",
        "",
    )


def test_foundry_generator_uses_hypothesis_and_invariant(tmp_path):
    result = investigate(TARGET)
    hypothesis = next(h for h in result.hypotheses if h.hypothesis_id == "H-AUTH-setWhitelist")
    generated = generate_access_control_test(
        hypothesis,
        "../../Target.sol",
        "AlchemixAccessControlFixture",
        tmp_path / "generated.t.sol",
    )
    source = generated.read_text(encoding="utf-8")
    assert "H-AUTH-setWhitelist" in source
    assert "vm.expectRevert();" in source
    assert "vm.prank(attacker);" in source
    assert "setWhitelist(account, true);" in source


def test_hypothesis_is_confirmed_only_by_vulnerable_failure_and_patched_pass():
    result = investigate(TARGET)
    hypothesis = next(h for h in result.hypotheses if h.hypothesis_id == "H-AUTH-setWhitelist")
    vulnerable = _execution("X-H-AUTH-setWhitelist", "vulnerable", 1, "FAIL", 1, 1)
    patched = _execution("X-H-AUTH-setWhitelist", "patched", 0, "PASS", 1, 0)
    outcome = classify_access_control_outcome(hypothesis, vulnerable, patched)
    assert outcome.hypothesis.status == "confirmed"
    assert "E-EXEC-H-AUTH-setWhitelist-VULNERABLE" in outcome.hypothesis.evidence_ids
    assert "E-EXEC-H-AUTH-setWhitelist-PATCHED" in outcome.hypothesis.evidence_ids


def test_unmeasurable_execution_cannot_confirm():
    result = investigate(TARGET)
    hypothesis = next(h for h in result.hypotheses if h.hypothesis_id == "H-AUTH-setWhitelist")
    vulnerable = _execution("X-H-AUTH-setWhitelist", "vulnerable", 0, "UNMEASURABLE", 0, 0)
    patched = _execution("X-H-AUTH-setWhitelist", "patched", 0, "PASS", 1, 0)
    outcome = classify_access_control_outcome(hypothesis, vulnerable, patched)
    assert outcome.hypothesis.status == "proposed"
    with pytest.raises(RuntimeError, match="UNMEASURABLE"):
        require_executed(vulnerable)


def test_hypothesis_stays_unconfirmed_without_measurable_differential():
    result = investigate(TARGET)
    hypothesis = next(h for h in result.hypotheses if h.hypothesis_id == "H-AUTH-setWhitelist")
    vulnerable = _execution("X-H-AUTH-setWhitelist", "vulnerable", 1, "FAIL", 1, 1)
    patched = _execution("X-H-AUTH-setWhitelist", "patched", 1, "FAIL", 1, 1)
    outcome = classify_access_control_outcome(hypothesis, vulnerable, patched)
    assert outcome.hypothesis.status == "proposed"
