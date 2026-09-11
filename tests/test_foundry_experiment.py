from pathlib import Path

from cydra.foundry import ExecutionResult, classify_access_control_outcome, generate_access_control_test
from cydra.pipeline import investigate


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "benchmarks" / "alchemix_missing_access_control" / "Target.sol"


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
    vulnerable = ExecutionResult("X-H-AUTH-setWhitelist", "vulnerable", ("forge", "test"), 1, False, "failed", "")
    patched = ExecutionResult("X-H-AUTH-setWhitelist", "patched", ("forge", "test"), 0, True, "passed", "")
    outcome = classify_access_control_outcome(hypothesis, vulnerable, patched)
    assert outcome.hypothesis.status == "confirmed"
    assert "E-EXEC-H-AUTH-setWhitelist-VULNERABLE" in outcome.hypothesis.evidence_ids
    assert "E-EXEC-H-AUTH-setWhitelist-PATCHED" in outcome.hypothesis.evidence_ids


def test_hypothesis_stays_unconfirmed_without_negative_control():
    result = investigate(TARGET)
    hypothesis = next(h for h in result.hypotheses if h.hypothesis_id == "H-AUTH-setWhitelist")
    vulnerable = ExecutionResult("X-H-AUTH-setWhitelist", "vulnerable", ("forge", "test"), 1, False, "failed", "")
    patched = ExecutionResult("X-H-AUTH-setWhitelist", "patched", ("forge", "test"), 1, False, "failed", "")
    outcome = classify_access_control_outcome(hypothesis, vulnerable, patched)
    assert outcome.hypothesis.status == "proposed"
