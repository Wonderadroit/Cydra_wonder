from pathlib import Path

import pytest

from cydra.models import ContractModel, Experiment, FunctionModel, Hypothesis, ParameterModel
from cydra.planned_foundry import generate_authorization_test_from_experiment


def _model(tmp_path: Path) -> ContractModel:
    source = tmp_path / "Target.sol"
    source.write_text(
        """pragma solidity ^0.8.20;
contract Target {
    uint256 public value;
    function withdraw(uint256 amount) external { value = amount; }
}
""",
        encoding="utf-8",
    )
    return ContractModel(
        name="Target",
        source=str(source),
        functions=(
            FunctionModel(
                name="withdraw",
                visibility="external",
                modifiers=(),
                writes=("value",),
                external_calls=(),
                line=3,
                parameters=(ParameterModel("amount", "uint256"),),
            ),
        ),
    )


def _hypothesis() -> Hypothesis:
    return Hypothesis(
        "H-AUTH-withdraw",
        "withdraw may mutate state for an unauthorized caller",
        "INV-AUTH-001",
        "withdraw",
        "arbitrary external caller",
        "state mutation",
    )


def _experiment(inputs=("1",)) -> Experiment:
    return Experiment(
        "X-H-AUTH-withdraw",
        "H-AUTH-withdraw",
        "call withdraw",
        ("authorization",),
        1.0,
        planned_inputs=inputs,
    )


def test_planned_constraint_value_reaches_generated_target_call(tmp_path: Path):
    generated = generate_authorization_test_from_experiment(
        _hypothesis(),
        _experiment(("7",)),
        "Target.sol",
        "Target",
        tmp_path / "generated.t.sol",
        _model(tmp_path),
    )
    source = generated.read_text(encoding="utf-8")
    assert "target.withdraw(7);" not in source
    assert 'abi.encodeWithSignature("withdraw(uint256)", 7)' in source
    assert "1" not in source.split("abi.encodeWithSignature", 1)[1].split(")", 1)[0]


def test_partial_planned_vector_fails_closed(tmp_path: Path):
    model = _model(tmp_path)
    hypothesis = _hypothesis()
    with pytest.raises(ValueError, match="planned input arity mismatch"):
        generate_authorization_test_from_experiment(
            hypothesis,
            _experiment(()),
            "Target.sol",
            "Target",
            tmp_path / "generated.t.sol",
            model,
        )
