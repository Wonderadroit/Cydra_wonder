from pathlib import Path

import pytest

from cydra.foundry import (
    ExecutionResult,
    generate_access_control_test,
    classify_access_control_outcome,
    require_executed,
)
from cydra.models import ContractModel, FunctionModel, Hypothesis, ParameterModel
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


def test_structural_auth_generator_uses_renamed_target_and_parameters(tmp_path):
    source = tmp_path / "RenamedTarget.sol"
    source.write_text(
        """pragma solidity ^0.8.20;
contract RenamedTarget {
    uint256 internal limit;
    function guardedLifecycle(uint256 value) external { limit = value; }
    function rotate(address recipient, uint256 value) external { limit = value; }
}
""",
        encoding="utf-8",
    )
    function = FunctionModel(
        name="rotate",
        visibility="external",
        modifiers=(),
        writes=("limit",),
        external_calls=(),
        line=4,
        parameters=(ParameterModel("recipient", "address"), ParameterModel("value", "uint256")),
    )
    hypothesis = Hypothesis(
        "H-AUTH-rotate",
        "An unprotected writer may mutate protected state.",
        "INV-AUTH-001",
        "rotate",
        "arbitrary caller",
        "unauthorized mutation",
    )
    model = ContractModel(
        "RenamedTarget",
        str(source),
        (FunctionModel("guardedLifecycle", "external", ("onlyGuardian",), ("limit",), (), 3), function),
        state_variables=("limit",),
    )
    generated = generate_access_control_test(
        hypothesis,
        "RenamedTarget.sol",
        "RenamedTarget",
        tmp_path / "generated.t.sol",
        contract_model=model,
    )
    generated_source = generated.read_text(encoding="utf-8")
    assert "rotate" in generated_source
    assert "abi.encodeWithSignature" in generated_source
    assert "target.rotate" not in generated_source
    assert "whiteList" not in generated_source
    assert "setWhitelist" not in generated_source
    assert "vm.record();" in generated_source
    assert "vm.accesses(address(target))" in generated_source


def test_structural_auth_generator_rejects_unresolved_custom_argument(tmp_path):
    function = FunctionModel(
        name="rotate",
        visibility="external",
        modifiers=(),
        writes=("limit",),
        external_calls=(),
        line=2,
        parameters=(ParameterModel("config", "UnknownStruct memory"),),
    )
    model = ContractModel("Target", str(tmp_path / "Target.sol"), (function,), state_variables=("limit",))
    hypothesis = Hypothesis(
        "H-AUTH-rotate",
        "An unprotected writer may mutate protected state.",
        "INV-AUTH-001",
        "rotate",
        "arbitrary caller",
        "unauthorized mutation",
    )
    (tmp_path / "Target.sol").write_text("contract Target {}", encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported authorization argument type"):
        generate_access_control_test(hypothesis, "Target.sol", "Target", tmp_path / "generated.t.sol", contract_model=model)


def test_hypothesis_is_confirmed_only_by_vulnerable_failure_and_patched_passes():
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
