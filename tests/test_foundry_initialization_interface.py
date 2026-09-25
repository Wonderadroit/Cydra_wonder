from cydra.foundry import generate_initialization_test
from cydra.interface_resolver import InterfaceMethod, ResolvedInterface
from cydra.models import ConstructorModel, ContractModel, Experiment, FunctionModel, Hypothesis, ParameterModel


def _hypothesis() -> Hypothesis:
    return Hypothesis(
        hypothesis_id="H-INIT-interface",
        claim="interface-aware initialization generation",
        invariant_id="INV-INIT-001",
        target_function="initialize",
        attacker_capability="external caller",
        expected_impact="initialization",
    )


def _model(
    name: str,
    constructor: tuple[ParameterModel, ...],
    parameters: tuple[ParameterModel, ...],
    *,
    inherits: tuple[str, ...] = (),
    declared_types: tuple[str, ...] = (),
    inherited_resolved_interfaces: tuple[ResolvedInterface, ...] = (),
) -> ContractModel:
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
        inherits=inherits,
        declared_types=declared_types,
        inherited_resolved_interfaces=inherited_resolved_interfaces,
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
    assert "try target.initialize(new address[](0), address(0xA11CE)) { } catch { }" in source
    assert "guardian()" not in source


def test_planned_inputs_override_initializer_fallback_arguments(tmp_path):
    model = _model(
        "SimpleInitializer",
        (),
        (
            ParameterModel("amount", "uint256"),
            ParameterModel("recipient", "address"),
        ),
    )
    experiment = Experiment(
        experiment_id="X-H-INIT-interface",
        hypothesis_id="H-INIT-interface",
        action="execute initialize",
        discriminates=("lifecycle",),
        cost=1.0,
        planned_inputs=("7", "address(0xCAFE)"),
    )
    output = generate_initialization_test(
        _hypothesis(),
        "../src/SimpleInitializer.sol",
        "SimpleInitializer",
        tmp_path / "generated.t.sol",
        contract_model=model,
        experiment=experiment,
    )
    source = output.read_text(encoding="utf-8")
    assert "try target.initialize(7, address(0xCAFE)) { } catch { }" in source
    assert "target.initialize(0, address(0));" not in source


def test_planned_input_arity_mismatch_fails_closed(tmp_path):
    model = _model(
        "SimpleInitializer",
        (),
        (
            ParameterModel("amount", "uint256"),
            ParameterModel("recipient", "address"),
        ),
    )
    experiment = Experiment(
        experiment_id="X-H-INIT-interface",
        hypothesis_id="H-INIT-interface",
        action="execute initialize",
        discriminates=("lifecycle",),
        cost=1.0,
        planned_inputs=("7",),
    )
    try:
        generate_initialization_test(
            _hypothesis(),
            "../src/SimpleInitializer.sol",
            "SimpleInitializer",
            tmp_path / "generated.t.sol",
            contract_model=model,
            experiment=experiment,
        )
    except ValueError as exc:
        assert "planned input arity mismatch" in str(exc)
    else:
        raise AssertionError("planned input arity mismatch must fail closed")


def test_model_aware_generator_qualifies_and_imports_inherited_custom_type(tmp_path):
    inherited = ResolvedInterface(
        name="IMinter",
        source_path="interfaces/IMinter.sol",
        resolution_method="relative_import",
        methods=(),
        declared_types=("AirdropParams",),
    )
    model = _model(
        "Minter",
        (
            ParameterModel("_voter", "address"),
            ParameterModel("_ve", "address"),
            ParameterModel("_rewardsDistributor", "address"),
        ),
        (ParameterModel("params", "AirdropParams", "memory"),),
        inherits=("IMinter",),
        inherited_resolved_interfaces=(inherited,),
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
    assert 'import { IMinter } from "interfaces/IMinter.sol";' in source
    assert source.count('import { IMinter } from "interfaces/IMinter.sol";') == 1
    assert "IMinter.AirdropParams memory parameter0;" in source
    function_start = source.index("function testInitializationInterfaceIsCallable()")
    function_body_start = source.index("{", function_start) + 1
    function_body_end = source.index("}", function_body_start)
    declaration_pos = source.index("IMinter.AirdropParams memory parameter0;")
    assert function_body_start < declaration_pos < function_body_end
    assert "Minter.AirdropParams memory parameter0;" not in source.replace("IMinter.AirdropParams memory parameter0;", "")
    assert "try target.initialize(parameter0) { } catch { }" in source
    assert "target.guardian()" not in source


def test_target_declared_custom_type_precedes_inherited_type(tmp_path):
    inherited = ResolvedInterface(
        name="IMinter",
        source_path="interfaces/IMinter.sol",
        resolution_method="relative_import",
        methods=(),
        declared_types=("AirdropParams",),
    )
    model = _model(
        "Minter",
        (),
        (ParameterModel("params", "AirdropParams", "memory"),),
        inherits=("IMinter",),
        declared_types=("AirdropParams",),
        inherited_resolved_interfaces=(inherited,),
    )
    output = generate_initialization_test(
        _hypothesis(),
        "../src/Minter.sol",
        "Minter",
        tmp_path / "generated.t.sol",
        contract_model=model,
    )
    source = output.read_text(encoding="utf-8")
    assert "Minter.AirdropParams memory parameter0;" in source
    assert "IMinter.AirdropParams memory parameter0;" not in source


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


def test_initializer_probe_avoids_zero_values_for_generic_scalar_preconditions(tmp_path):
    from cydra.foundry import generate_initialization_test
    model = _model(
        "SimpleInitializer",
        (),
        (ParameterModel("owner", "address"), ParameterModel("amount", "uint256")),
    )
    output = generate_initialization_test(_hypothesis(), "../src/SimpleInitializer.sol", "SimpleInitializer", tmp_path / "generated.t.sol", contract_model=model)
    source = output.read_text(encoding="utf-8")
    assert "address(0xA11CE)" in source
    assert "address(0)" not in source
    assert "try target.initialize(" in source


def test_initializer_probe_synthesizes_aligned_future_timestamp(tmp_path):
    from cydra.foundry import generate_initialization_test
    path = tmp_path / "TimedInitializer.sol"
    path.write_text('''
        contract TimedInitializer {
            uint256 public rewardStartTime;
            function initialize(uint256 rewardStartTime) external {
                require(rewardStartTime > block.timestamp);
                require(rewardStartTime % 86400 == 0);
                rewardStartTime = rewardStartTime;
            }
        }
    ''', encoding="utf-8")
    model = _model("TimedInitializer", (), (ParameterModel("rewardStartTime", "uint256"),))
    model = ContractModel(**{**model.__dict__, "source": str(path)})
    output = generate_initialization_test(_hypothesis(), "../src/TimedInitializer.sol", "TimedInitializer", tmp_path / "generated.t.sol", contract_model=model)
    source = output.read_text(encoding="utf-8")
    assert "((block.timestamp / 86400) + 2) * 86400" in source


def test_model_aware_generator_imports_bare_resolved_interface_initializer_type(tmp_path):
    interface = ResolvedInterface(
        name="IERC20Metadata",
        source_path="lib/openzeppelin-contracts/contracts/token/ERC20/extensions/IERC20Metadata.sol",
        resolution_method="project_relative",
        methods=(InterfaceMethod("decimals", (), ("uint8",)),),
    )
    model = _model(
        "VaultFixture",
        (),
        (
            ParameterModel("asset_", "IERC20Metadata"),
            ParameterModel("owner", "address"),
        ),
        inherited_resolved_interfaces=(interface,),
    )
    output = generate_initialization_test(
        _hypothesis(),
        "../src/Vault.sol",
        "VaultFixture",
        tmp_path / "generated.t.sol",
        contract_model=model,
    )
    source = output.read_text(encoding="utf-8")
    assert 'import { IERC20Metadata } from "lib/openzeppelin-contracts/contracts/token/ERC20/extensions/IERC20Metadata.sol";' in source
    assert "IERC20Metadata(address(tokenStub))" in source
    assert "IERC20Metadata memory parameter0;" not in source


def test_interface_initializer_parameter_is_not_declared_with_memory(tmp_path):
    interface = ResolvedInterface(
        name="IERC20Metadata",
        source_path="interfaces/IERC20Metadata.sol",
        resolution_method="relative_import",
        methods=(InterfaceMethod("decimals", (), ("uint8",)),),
    )
    source_path = tmp_path / "Vault.sol"
    source_path.write_text(
        "interface IERC20Metadata { function decimals() external view returns (uint8); }\n"
        "contract Vault { function initialize(IERC20Metadata asset_) external {} }\n",
        encoding="utf-8",
    )
    model = _model(
        "Vault",
        (),
        (ParameterModel("asset_", "IERC20Metadata"),),
        inherited_resolved_interfaces=(interface,),
    )
    model = ContractModel(**{**model.__dict__, "source": str(source_path)})
    output = generate_initialization_test(
        _hypothesis(),
        "../src/Vault.sol",
        "Vault",
        tmp_path / "generated.t.sol",
        contract_model=model,
    )
    source = output.read_text(encoding="utf-8")
    assert "IERC20Metadata memory parameter0;" not in source
    assert "IERC20Metadata parameter0;" in source
