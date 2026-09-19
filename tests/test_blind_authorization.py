from pathlib import Path

from cydra.authorization_runtime import classify_authorization_blind_execution
from cydra.blind_authorization import generate_blind_authorization_test_from_experiment
from cydra.foundry import ExecutionResult
from cydra.models import ContractModel, Experiment, FunctionModel, Hypothesis, ParameterModel


def _hypothesis():
    return Hypothesis(
        "H-AUTH-setWhitelist",
        "candidate",
        "INV-AUTH-001",
        "setWhitelist",
        "arbitrary external caller",
        "administrative state mutation",
    )


def _execution(status, stdout="", executed=True, tests_failed=0):
    return ExecutionResult(
        "X-H-AUTH-setWhitelist",
        "blind",
        ("forge", "test"),
        1 if status == "FAIL" else 0,
        executed,
        1,
        tests_failed,
        status,
        stdout,
        "",
    )


def test_blind_auth_security_assertion_confirms_without_patched_target():
    outcome = classify_authorization_blind_execution(
        _hypothesis(),
        _execution("FAIL", "assertion failed: CYDRA_SECURITY_ASSERTION: unauthorized caller mutated modeled administrative state", tests_failed=1),
    )
    assert outcome.internal_status == "confirmed"
    assert outcome.benchmark_status == "confirmed"
    assert outcome.evidence.evidence_id == "E-EXEC-H-AUTH-setWhitelist-AUTHORIZATION-BLIND"


def test_blind_auth_pass_is_not_confirmed():
    outcome = classify_authorization_blind_execution(_hypothesis(), _execution("PASS"))
    assert outcome.internal_status == "rejected"
    assert outcome.benchmark_status == "not_confirmed"


def test_blind_auth_tool_failure_is_not_a_finding():
    outcome = classify_authorization_blind_execution(
        _hypothesis(),
        _execution("FAIL", "compilation failed", executed=True, tests_failed=0),
    )
    assert outcome.internal_status == "proposed"
    assert outcome.benchmark_status == "proposed"


def test_blind_auth_renderer_uses_planned_abi_vector(tmp_path: Path):
    model = ContractModel(
        "Fixture",
        str(tmp_path / "Fixture.sol"),
        (
            FunctionModel(
                "setWhitelist",
                "external",
                (),
                ("whiteList",),
                (),
                4,
                (ParameterModel("account", "address"), ParameterModel("state", "bool")),
            ),
        ),
    )
    hypothesis = _hypothesis()
    experiment = Experiment(
        "X-H-AUTH-setWhitelist",
        hypothesis.hypothesis_id,
        "call",
        ("violation", "preservation"),
        1.0,
        planned_inputs=("address(0xCAFE)", "true"),
    )
    output = generate_blind_authorization_test_from_experiment(
        hypothesis, experiment, "../Fixture.sol", "Fixture", tmp_path / "generated.t.sol", model
    )
    source = output.read_text(encoding="utf-8")
    assert "address(0xCAFE)" in source
    assert "true" in source
    assert "CYDRA_SECURITY_ASSERTION" in source
    assert "Patched" not in source
