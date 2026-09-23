from pathlib import Path

import pytest

from cydra.models import ConstructorModel, ContractModel, Experiment, FunctionModel, Hypothesis, ParameterModel
from cydra.planned_foundry import generate_authorization_test_from_experiment


def _model(tmp_path: Path) -> ContractModel:
    source = tmp_path / "Target.sol"
    source.write_text(
        """pragma solidity ^0.8.20;
contract Target {
    uint256 public value;
    function withdraw(uint256 amount, address recipient) external { value = amount; recipient; }
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
                parameters=(
                    ParameterModel("amount", "uint256"),
                    ParameterModel("recipient", "address"),
                ),
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


def _experiment(inputs=("1", "address(0xCAFE)")) -> Experiment:
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
        _experiment(("7", "address(0xBEEF)")),
        "Target.sol",
        "Target",
        tmp_path / "generated.t.sol",
        _model(tmp_path),
    )
    source = generated.read_text(encoding="utf-8")
    assert "try target.withdraw(7, address(0xBEEF))" in source
    assert "try target.withdraw(1, address(0xCAFE))" not in source


def test_partial_planned_vector_fails_closed(tmp_path: Path):
    model = _model(tmp_path)
    hypothesis = _hypothesis()
    with pytest.raises(ValueError, match="planned input arity mismatch"):
        generate_authorization_test_from_experiment(
            hypothesis,
            _experiment(("7",)),
            "Target.sol",
            "Target",
            tmp_path / "generated.t.sol",
            model,
        )


def test_authorization_renderer_materializes_constructible_state_setup(tmp_path: Path):
    (tmp_path / "foundry.toml").write_text("[profile.default]\\n", encoding="utf-8")
    source = tmp_path / "Target.sol"
    source.write_text("pragma solidity ^0.8.20; contract Target { address[] public items; function withdraw(uint256 amount, address recipient) external { amount; recipient; } function seed(address item) external { items.push(item); } }", encoding="utf-8")
    target = FunctionModel(
        name="withdraw", visibility="external", modifiers=(), writes=(), external_calls=(), line=1,
        parameters=(ParameterModel("amount", "uint256"), ParameterModel("recipient", "address")),
        state_predicates=("items.length == 0",),
        state_predicate_polarities=(("items.length == 0", "must_not_hold"),),
    )
    seed = FunctionModel(
        name="seed", visibility="external", modifiers=(), writes=(), external_calls=(("items", "push"),), line=1,
        parameters=(ParameterModel("item", "address"),),
    )
    model = ContractModel("Target", str(source), (target, seed), pragma="^0.8.20")
    generated = generate_authorization_test_from_experiment(
        _hypothesis(), _experiment(("7", "address(0xBEEF)")), "Target.sol", "Target", tmp_path / "test" / "generated.t.sol", model
    )
    rendered = generated.read_text(encoding="utf-8")
    assert "vm.prank(attacker);\\n        target.seed(address(0xCAFE));" in rendered
    assert "execution-readiness setup failed" in rendered


def test_authorization_renderer_emits_constructor_arguments_and_imports_interface(tmp_path: Path):
    (tmp_path / "foundry.toml").write_text("[profile.default]\n", encoding="utf-8")
    (tmp_path / "IERC20.sol").write_text("interface IERC20 {}\n", encoding="utf-8")
    source = tmp_path / "Target.sol"
    source.write_text(
        'pragma solidity ^0.8.20;\nimport "./IERC20.sol";\n'
        'contract Target { constructor(IERC20 token, uint256 value) {} '
        'function withdraw(uint256 amount) external {} }\n',
        encoding="utf-8",
    )
    model = ContractModel(
        "Target",
        str(source),
        (
            FunctionModel(
                name="withdraw",
                visibility="external",
                modifiers=(),
                writes=(),
                external_calls=(),
                line=4,
                parameters=(ParameterModel("amount", "uint256"), ParameterModel("recipient", "address")),
            ),
        ),
        constructor=ConstructorModel(
            (ParameterModel("token", "IERC20"), ParameterModel("value", "uint256")),
            1,
        ),
        pragma="^0.8.20",
    )
    generated = generate_authorization_test_from_experiment(
        _hypothesis(),
        _experiment(("7", "address(0xBEEF)")),
        "Target.sol",
        "Target",
        tmp_path / "test" / "generated.t.sol",
        model,
    )
    rendered = generated.read_text(encoding="utf-8")
    assert 'import { IERC20 } from "../IERC20.sol";' in rendered
    assert "target = new Target(IERC20(address(0)), 0);" in rendered


def test_authorization_renderer_resolves_indirect_contract_constructor_type(tmp_path: Path):
    (tmp_path / "foundry.toml").write_text("[profile.default]\n", encoding="utf-8")
    (tmp_path / "interfaces").mkdir()
    (tmp_path / "interfaces" / "Token.sol").write_text(
        "contract ERC20 { constructor(string memory, string memory, uint8) {} }\n", encoding="utf-8"
    )
    source = tmp_path / "Target.sol"
    source.write_text(
        'pragma solidity ^0.8.20;\nimport { ERC20 } from "./interfaces/Token.sol";\n'
        'contract Target { constructor(ERC20 token) {} '
        'function withdraw(uint256 amount) external {} }\n',
        encoding="utf-8",
    )
    model = ContractModel(
        "Target",
        str(source),
        (
            FunctionModel(
                name="withdraw",
                visibility="external",
                modifiers=(),
                writes=(),
                external_calls=(),
                line=3,
                parameters=(ParameterModel("amount", "uint256"),),
            ),
        ),
        constructor=ConstructorModel((ParameterModel("token", "ERC20"),), 1),
        pragma="^0.8.20",
    )
    generated = generate_authorization_test_from_experiment(
        _hypothesis(),
        _experiment(("7",)),
        "Target.sol",
        "Target",
        tmp_path / "test" / "generated.t.sol",
        model,
    )
    rendered = generated.read_text(encoding="utf-8")
    assert 'import { ERC20 } from "../interfaces/Token.sol";' in rendered
    assert "target = new Target(ERC20(address(constructorAsset)));" in rendered
