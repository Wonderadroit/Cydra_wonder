from pathlib import Path

import pytest

from cydra.foundry import (
    ExecutionResult,
    generate_access_control_test,
    classify_access_control_outcome,
    classify_experiment_outcome,
    require_executed,
)
from cydra.models import ContractModel, FunctionModel, Hypothesis, ParameterModel, Experiment, Invariant
from cydra.pipeline import ReasoningContribution
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


def test_future_reasoning_class_crosses_class_neutral_causal_classifier():
    hypothesis = Hypothesis(
        "H-FUTURE-causal",
        "rebalance may violate the modeled invariant under a boundary input",
        "INV-FUTURE-046",
        "rebalance",
        "externally callable actor",
        "incorrect position state",
    )
    vulnerable = _execution("X-H-FUTURE-causal-VULNERABLE", "vulnerable", 1, "FAIL", 1, 1)
    patched = _execution("X-H-FUTURE-causal-PATCHED", "patched", 0, "PASS", 1, 0)

    outcome = classify_experiment_outcome(hypothesis, vulnerable, patched)

    assert outcome.hypothesis.status == "confirmed"
    assert outcome.hypothesis.invariant_id == "INV-FUTURE-046"
    assert outcome.hypothesis.target_function == "rebalance"
    assert [item.evidence_id for item in outcome.evidence] == [
        "E-EXEC-H-FUTURE-causal-VULNERABLE",
        "E-EXEC-H-FUTURE-causal-PATCHED",
    ]


def test_future_reasoning_surface_enters_pipeline_without_vulnerability_class_branch(tmp_path):
    source = tmp_path / "FutureSurface.sol"
    source.write_text(
        """pragma solidity ^0.8.20;
contract FutureSurface {
    uint256 internal position;
    function rebalance(uint256 amount) external { position += amount; }
    function settle(uint256 amount) external { position -= amount; }
}
""",
        encoding="utf-8",
    )

    def future_surface(contract, _semantic):
        function = next(item for item in contract.functions if item.name == "rebalance")
        invariant = Invariant(
            "INV-FUTURE-046",
            "State transitions must preserve the modeled position invariant.",
            "future reasoning surface",
            0.70,
        )
        hypothesis = Hypothesis(
            "H-FUTURE-rebalance",
            "rebalance may violate the modeled position invariant under a boundary input.",
            invariant.invariant_id,
            function.name,
            "externally callable actor",
            "incorrect position state",
            evidence_ids=(f"E-MODEL-{function.name}",),
        )
        return ReasoningContribution((invariant,), (hypothesis,))

    def future_planner(hypothesis):
        return Experiment(
            "X-FUTURE-rebalance",
            hypothesis.hypothesis_id,
            "Execute the candidate transition at a boundary input and compare the modeled invariant.",
            ("state remains valid", "state becomes invalid"),
            1.0,
            target_function=hypothesis.target_function,
        )

    result = investigate(
        source,
        reasoning_surfaces=(future_surface,),
        experiment_planner=future_planner,
    )
    hypothesis = next(item for item in result.hypotheses if item.hypothesis_id == "H-FUTURE-rebalance")
    experiment = next(item for item in result.experiments if item.hypothesis_id == hypothesis.hypothesis_id)

    assert hypothesis.invariant_id == "INV-FUTURE-046"
    assert experiment.target_function == "rebalance"
    assert experiment.experiment_id == "X-FUTURE-rebalance"

    vulnerable = _execution("X-FUTURE-rebalance-VULNERABLE", "vulnerable", 1, "FAIL", 1, 1)
    patched = _execution("X-FUTURE-rebalance-PATCHED", "patched", 0, "PASS", 1, 0)
    outcome = classify_experiment_outcome(hypothesis, vulnerable, patched)
    assert outcome.hypothesis.status == "confirmed"


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


def test_foundry_execution_timeout_fails_closed(monkeypatch, tmp_path):
    import cydra.foundry as foundry

    test_path = tmp_path / "generated.t.sol"
    test_path.write_text("// test", encoding="utf-8")

    def timeout(*args, **kwargs):
        raise __import__("subprocess").TimeoutExpired(kwargs.get("args", args[0] if args else "forge"), 1, output="partial", stderr="still running")

    monkeypatch.setattr(foundry.subprocess, "run", timeout)
    monkeypatch.setenv("CYDRA_EXPERIMENT_TIMEOUT_SECONDS", "2")

    result = foundry.run_foundry_test(tmp_path, test_path, "X-timeout", "blind")
    assert result.status == "UNMEASURABLE"
    assert result.executed is False
    assert result.tests_run == 0
    assert result.exit_code == 124
    assert "CYDRA experiment timeout after 2s" in result.stderr


def test_foundry_execution_timeout_budget_must_be_positive(monkeypatch):
    import cydra.foundry as foundry

    monkeypatch.setenv("CYDRA_EXPERIMENT_TIMEOUT_SECONDS", "0")
    with pytest.raises(ValueError, match="greater than zero"):
        foundry._experiment_timeout_seconds()
