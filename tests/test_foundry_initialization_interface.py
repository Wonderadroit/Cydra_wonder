from cydra.foundry import generate_initialization_test
from cydra.models import ConstructorModel, ContractModel, FunctionModel, Hypothesis, ParameterModel


def _hypothesis() -> Hypothesis:
    return Hypothesis(
        hypothesis_id="H-INIT-interface",
        claim="interface-aware initialization generation",
        invariant_id="INV-INIT-001",
        target_function="initialize",
        attacker_capability="external caller",
        expected_impact="initialization",
    )


def _model(name: str, constructor: tuple[ParameterModel, ...], parameters: tuple[ParameterModel, ...]) -> ContractModel:
    return ContractModel(
        name=name,
        source=f"{name}.sol",
        constructor=ConstructorModel(constructor, 2),
        functions=(
            FunctionModel(
                name="initialize",
                visibility="external",
                modifiers=(),
                writes=(),
                external_calls=(),
                line=5,
                parameters=parameters,
                authorization_predicates=(),
            ),
        ),
    )


def test_model_aware_generator_consumes_constructor_and_parameters(tmp_path):
    model = _model(
        "LiquidClawFixture",
        (
            ParameterModel("_voter", "address"),
            ParameterModel("_ve", "address"),
            ParameterModel("_registry", "address"),
        ),
        (
            ParameterModel("_tokens", "address[]", "calldata"),
            ParameterModel("_minter", "address"),
        ),
    )
    output = generate_initialization_test(
        _hypothesis(),
        "../src/LiquidClaw.sol",
        "LiquidClawFixture",
        tmp_path / "generated.t.sol",
        contract_model=model,
    )
    source = output.read_text(encoding="utf-8")
    assert "new LiquidClawFixture(address(0), address(0), address(0))" in source
    assert "target.initialize(new address[](0), address(0));" in source
    assert "guardian()" not in source


def test_model_aware_generator_emits_custom_type_without_guessing_its_fields(tmp_path):
    model = _model(
        "Minter",
        (
            ParameterModel("_voter", "address"),
            ParameterModel("_ve", "address"),
            ParameterModel("_rewardsDistributor", "address"),
        ),
        (ParameterModel("params", "AirdropParams", "memory"),),
    )
    output = generate_initialization_test(
        _hypothesis(),
        "../src/Minter.sol",
        "Minter",
        tmp_path / "generated.t.sol",
        contract_model=model,
    )
    source = output.read_text(encoding="utf-8")
    assert "new Minter(address(0), address(0), address(0))" in source
    assert "Minter.AirdropParams memory parameter0;" in source
    assert "target.initialize(parameter0);" in source
    assert "target.guardian()" not in source


def test_legacy_generator_path_is_unchanged_without_model(tmp_path):
    output = generate_initialization_test(
        _hypothesis(),
        "../src/Target.sol",
        "WormholeInitializationFixture",
        tmp_path / "generated.t.sol",
    )
    source = output.read_text(encoding="utf-8")
    assert "new WormholeInitializationFixture();" in source
    assert "abi.encodeWithSelector(target.initialize.selector, attacker)" in source
    assert "target.guardian() != attacker" in source
