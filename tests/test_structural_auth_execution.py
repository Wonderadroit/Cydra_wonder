from pathlib import Path

import pytest

from cydra.models import ContractModel, FunctionModel, Hypothesis, ParameterModel
from cydra.structural_auth_execution import generate_structural_authorization_test


def _model(parameters=()):
    return ContractModel(
        name="RenamedTarget",
        source="fixture.sol",
        functions=(
            FunctionModel(
                name="configure",
                visibility="external",
                modifiers=(),
                writes=("settings",),
                external_calls=(),
                line=10,
                parameters=tuple(parameters),
            ),
        ),
        pragma="^0.8.20",
    )


def _hypothesis():
    return Hypothesis(
        hypothesis_id="H-AUTH-configure",
        claim="unauthorized caller can mutate privileged state",
        invariant_id="INV-AUTH-001",
        target_function="configure",
        attacker_capability="arbitrary caller",
        expected_impact="privileged state mutation",
    )


def test_generation_uses_typed_interface_call_and_not_benchmark_names(tmp_path: Path):
    model = _model((ParameterModel("account", "address"), ParameterModel("enabled", "bool")))
    path = generate_structural_authorization_test(
        _hypothesis(), model, "../Target.sol", model.name, tmp_path / "generated.t.sol"
    )
    source = path.read_text(encoding="utf-8")
    assert "interface CydraStructuralAuthTarget" in source
    assert "function configure(address account, bool enabled) external;" in source
    assert "CydraStructuralAuthTarget(address(target)).configure(address(0xCAFE), false);" in source
    assert "setWhitelist" not in source
    assert "quoteMint" not in source


def test_generation_rejects_nonzero_constructor_dependencies(tmp_path: Path):
    from cydra.models import ConstructorModel

    model = _model()
    model = ContractModel(
        name=model.name,
        source=model.source,
        functions=model.functions,
        constructor=ConstructorModel(
            parameters=(ParameterModel("governance", "address"),),
            line=5,
        ),
        pragma=model.pragma,
    )
    with pytest.raises(ValueError, match="zero-argument constructor"):
        generate_structural_authorization_test(
            _hypothesis(), model, "../Target.sol", model.name, tmp_path / "generated.t.sol"
        )


def test_generation_rejects_unresolved_custom_type(tmp_path: Path):
    model = _model((ParameterModel("config", "Config"),))
    with pytest.raises(ValueError, match="unsupported structural authorization interface type"):
        generate_structural_authorization_test(
            _hypothesis(), model, "../Target.sol", model.name, tmp_path / "generated.t.sol"
        )
