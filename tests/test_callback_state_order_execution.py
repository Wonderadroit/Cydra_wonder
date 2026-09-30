from pathlib import Path

from cydra.callback_state_order_execution import generate_callback_state_order_test
from cydra.models import ContractModel, Experiment, FunctionModel, Hypothesis, ParameterModel


def test_callback_runtime_generator_builds_one_shot_reentrant_harness(tmp_path: Path):
    source = tmp_path / "Callback.sol"
    source.write_text(
        """
        pragma solidity ^0.8.20;
        contract Callback {
            uint256 public settled;
            function execute(uint256 amount) external {
                settled = amount;
            }
        }
        """,
        encoding="utf-8",
    )
    function = FunctionModel(
        name="execute",
        visibility="external",
        modifiers=(),
        writes=("settled",),
        external_calls=("hook.beforeAction()",),
        line=4,
        parameters=(ParameterModel(name="amount", type="uint256"),),
    )
    contract = ContractModel(
        name="Callback",
        source=str(source),
        functions=(function,),
        pragma="^0.8.20",
    )
    hypothesis = Hypothesis(
        "H-CALLBACK-STATE-ORDER-execute",
        "callback ordering may expose intermediate state",
        "INV-CALLBACK-STATE-ORDER-execute",
        "execute",
        "caller-controlled callback",
        "reentrant state bypass",
    )
    experiment = Experiment(
        "X-H-CALLBACK-STATE-ORDER-execute",
        hypothesis.hypothesis_id,
        "reenter",
        ("reentry succeeds",),
        2.0,
        planned_inputs=("1",),
        target_function="execute",
    )
    output = tmp_path / "test" / "generated.t.sol"
    generate_callback_state_order_test(
        hypothesis, experiment, str(source), "Callback", output, contract
    )
    rendered = output.read_text(encoding="utf-8")
    assert "CydraReentrantCaller" in rendered
    assert "callbackObserved" in rendered
    assert "reentrySucceeded" in rendered
    assert 'abi.encodeCall(target.execute, (1))' in rendered


def test_callback_runtime_generator_rejects_incomplete_input_vector(tmp_path: Path):
    source = tmp_path / "Callback.sol"
    source.write_text("pragma solidity ^0.8.20; contract Callback {}", encoding="utf-8")
    function = FunctionModel(
        name="execute",
        visibility="external",
        modifiers=(),
        writes=(),
        external_calls=(),
        line=1,
        parameters=(ParameterModel(name="amount", type="uint256"),),
    )
    contract = ContractModel("Callback", str(source), (function,), pragma="^0.8.20")
    hypothesis = Hypothesis(
        "H-CALLBACK-STATE-ORDER-execute", "claim", "INV-CALLBACK-STATE-ORDER-execute",
        "execute", "callback", "impact",
    )
    experiment = Experiment(
        "X-H-CALLBACK-STATE-ORDER-execute", hypothesis.hypothesis_id,
        "reenter", (), 2.0, planned_inputs=(), target_function="execute",
    )
    try:
        generate_callback_state_order_test(
            hypothesis, experiment, str(source), "Callback",
            tmp_path / "test" / "generated.t.sol", contract,
        )
    except ValueError as error:
        assert "arity mismatch" in str(error)
    else:
        raise AssertionError("expected incomplete callback input vector to fail closed")


def test_callback_runtime_generator_emits_initializer_declarations_before_call(tmp_path: Path, monkeypatch):
    source = tmp_path / "Callback.sol"
    source.write_text(
        "pragma solidity ^0.8.20; contract Callback { struct HelperConfig { uint256 value; } }",
        encoding="utf-8",
    )
    function = FunctionModel(
        name="execute", visibility="external", modifiers=(), writes=(),
        external_calls=("hook.beforeAction()",), line=4,
        parameters=(ParameterModel(name="amount", type="uint256"),),
    )
    initializer = FunctionModel(
        name="initialize", visibility="external", modifiers=(), writes=(),
        external_calls=(), line=3,
        parameters=(
            ParameterModel(name="config", type="HelperConfig"),
            ParameterModel(name="allowedRecipients", type="address[]"),
        ),
    )
    contract = ContractModel(
        name="Callback", source=str(source), functions=(initializer, function), pragma="^0.8.20",
    )
    hypothesis = Hypothesis(
        "H-CALLBACK-STATE-ORDER-execute", "claim", "INV-CALLBACK-STATE-ORDER-execute",
        "execute", "callback", "impact",
    )
    experiment = Experiment(
        "X-H-CALLBACK-STATE-ORDER-execute", hypothesis.hypothesis_id,
        "reenter", (), 2.0, planned_inputs=("1",), target_function="execute",
    )

    def fake_lifecycle(*args, **kwargs):
        path = Path(args[3])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "function testInitializationInterfaceIsCallable() public {\n"
            "    HelperConfig memory parameter0;\n"
            "    target.initialize(parameter0, new address[](0));\n"
            "}\n",
            encoding="utf-8",
        )
        return path

    monkeypatch.setattr("cydra.callback_state_order_execution.generate_initialization_test", fake_lifecycle)
    monkeypatch.setattr(
        "cydra.callback_state_order_execution._callback_metadata_setup",
        lambda *args, **kwargs: {"input_name": "cydraCallbackInput", "setup": "uint256 marker = 1;", "imports": set()},
    )

    output = tmp_path / "test" / "generated.t.sol"
    generate_callback_state_order_test(hypothesis, experiment, str(source), "Callback", output, contract)
    rendered = output.read_text(encoding="utf-8")
    declaration = "HelperConfig memory parameter0;"
    initializer_call = "target.initialize(parameter0, CydraCallerSet.one(cydraAttacker));"
    assert declaration in rendered
    assert initializer_call in rendered
    assert rendered.index(declaration) < rendered.index(initializer_call)
    assert "event CydraCallbackObservation(bool callbackObserved, bool reentrySucceeded);" in rendered


def test_callback_execution_context_uses_conservative_timestamp_extreme(tmp_path: Path):
    from cydra.callback_state_order_execution import _execution_context_warp

    source = tmp_path / "Context.sol"
    source.write_text(
        """
        pragma solidity ^0.8.20;
        contract Context {
            function runAction() external { verify(); }
            function verify() internal {
                require(block.timestamp <= deadline);
            }
            uint256 deadline;
        }
        """,
        encoding="utf-8",
    )
    run_action = FunctionModel(
        name="runAction",
        visibility="external",
        modifiers=(),
        writes=(),
        external_calls=(),
        line=4,
    )
    verify = FunctionModel(
        name="verify",
        visibility="internal",
        modifiers=(),
        writes=(),
        external_calls=(),
        line=5,
        execution_predicates=("block.timestamp <= deadline",),
        execution_predicate_polarities=(("block.timestamp <= deadline", "must_hold"),),
    )
    contract = ContractModel(
        "Context",
        str(source),
        (run_action, verify),
        pragma="^0.8.20",
    )
    assert _execution_context_warp(contract, run_action) is None
    guarded = FunctionModel(
        name="verifyGuarded",
        visibility="internal",
        modifiers=(),
        writes=(),
        external_calls=(),
        line=5,
        execution_predicates=("block.timestamp > deadline",),
        execution_predicate_polarities=(("block.timestamp > deadline", "must_not_hold"),),
    )
    guarded_contract = ContractModel(
        "Context",
        str(source),
        (run_action, guarded),
        pragma="^0.8.20",
    )
    assert _execution_context_warp(guarded_contract, run_action) == "vm.warp(0);"


def test_callback_runtime_generator_emits_causal_reentry_oracle(tmp_path: Path):
    source = tmp_path / "Callback.sol"
    source.write_text("pragma solidity ^0.8.20; contract Callback {}", encoding="utf-8")
    function = FunctionModel(
        name="execute", visibility="external", modifiers=(), writes=(),
        external_calls=(), line=1, parameters=(ParameterModel(name="amount", type="uint256"),),
    )
    contract = ContractModel("Callback", str(source), (function,), pragma="^0.8.20")
    hypothesis = Hypothesis(
        "H-CALLBACK-STATE-ORDER-execute", "claim", "INV-CALLBACK-STATE-ORDER-execute",
        "execute", "callback", "impact",
    )
    experiment = Experiment(
        "X-H-CALLBACK-STATE-ORDER-execute", hypothesis.hypothesis_id,
        "reenter", (), 2.0, planned_inputs=("1",), target_function="execute",
    )
    # This test targets the legacy renderer only when no initializer exists.
    output = tmp_path / "test" / "generated.t.sol"
    generate_callback_state_order_test(hypothesis, experiment, str(source), "Callback", output, contract)
    rendered = output.read_text(encoding="utf-8")
    assert "assertFalse(attacker.reentrySucceeded()" in rendered
    assert "CydraCallbackObservation" in rendered


def test_callback_classifier_uses_asserted_observation_not_stdout():
    from types import SimpleNamespace
    from scripts.run_benchmark_blind import _classify_callback_state_order_execution

    passing = SimpleNamespace(executed=True, tests_failed=0, stdout="", stderr="")
    assert _classify_callback_state_order_execution(passing) == (
        "rejected",
        "callback was observed and the reentrant invocation was blocked",
    )

    candidate = SimpleNamespace(
        executed=True,
        tests_failed=1,
        stdout='Error: reentrant callback succeeded',
        stderr="",
    )
    assert _classify_callback_state_order_execution(candidate) == (
        "candidate",
        "callback was observed and the reentrant invocation succeeded",
    )


def test_callback_runtime_generator_materializes_namespaced_constructor_struct(tmp_path):
    interface = tmp_path / "IMerkle.sol"
    interface.write_text(
        "interface IMerkle { struct MerkleConstructorArgs { uint128 levels; address poseidon2; } }\n",
        encoding="utf-8",
    )
    source = tmp_path / "Callback.sol"
    source.write_text(
        'pragma solidity ^0.8.20; import "./IMerkle.sol"; '
        'contract Callback { constructor(IMerkle.MerkleConstructorArgs memory args) {} '
        'function execute(uint256 amount) external {} }\n',
        encoding="utf-8",
    )
    function = FunctionModel(
        name="execute", visibility="external", modifiers=(), writes=(),
        external_calls=(), line=4,
        parameters=(ParameterModel(name="amount", type="uint256"),),
    )
    from cydra.models import ConstructorModel
    contract = ContractModel(
        "Callback", str(source), (function,), pragma="^0.8.20",
        constructor=ConstructorModel(
            (ParameterModel("args", "IMerkle.MerkleConstructorArgs"),), 2
        ),
    )
    hypothesis = Hypothesis(
        "H-CALLBACK-STATE-ORDER-execute", "claim", "INV-CALLBACK-STATE-ORDER-execute",
        "execute", "callback", "impact",
    )
    experiment = Experiment(
        "X-H-CALLBACK-STATE-ORDER-execute", hypothesis.hypothesis_id,
        "reenter", (), 2.0, planned_inputs=("1",), target_function="execute",
    )
    output = tmp_path / "test" / "generated.t.sol"
    generate_callback_state_order_test(hypothesis, experiment, str(source), "Callback", output, contract)
    rendered = output.read_text(encoding="utf-8")
    assert "new Callback((0, address(0)));" in rendered



def test_callback_caller_binding_discovery_follows_modeled_internal_predicates(tmp_path):
    from cydra.callback_state_order_execution import _caller_bound_parameter_paths

    source = tmp_path / "Callback.sol"
    source.write_text(
        "pragma solidity ^0.8.20; contract Callback { "
        "function execute(Data calldata data) external { check(data); } "
        "function check(Data calldata data) internal { require(data.endpoint == msg.sender); } "
        "struct Data { address endpoint; } }",
        encoding="utf-8",
    )
    execute = FunctionModel(
        name="execute", visibility="external", modifiers=(), writes=(),
        external_calls=(), line=1,
        parameters=(ParameterModel(name="data", type="Data"),),
        internal_calls=("check",),
    )
    check = FunctionModel(
        name="check", visibility="internal", modifiers=(), writes=(),
        external_calls=(), line=1,
        parameters=(ParameterModel(name="data", type="Data"),),
        execution_predicates=("data.endpoint == msg.sender",),
    )
    contract = ContractModel("Callback", str(source), (execute, check), pragma="^0.8.20")
    assert _caller_bound_parameter_paths(contract, execute) == ("data.endpoint",)


def test_callback_state_setup_uses_target_derived_mapping_relation(tmp_path: Path):
    from cydra.callback_state_order_execution import _state_setup_source

    source = tmp_path / "Callback.sol"
    source.write_text(
        """
        pragma solidity ^0.8.20;
        contract Callback {
            mapping(uint256 => address) registry;
            function execute(Data calldata data) external {
                check(data);
            }
            function check(Data calldata data) internal {
                require(registry[data.key] == data.endpoint);
            }
            function register(uint256 key, address endpoint) external {
                registry[key] = endpoint;
            }
            struct Data { uint256 key; address endpoint; }
        }
        """,
        encoding="utf-8",
    )
    execute = FunctionModel(
        name="execute", visibility="external", modifiers=(), writes=(),
        external_calls=(), line=5,
        parameters=(ParameterModel("data", "Data", "calldata"),),
        internal_calls=("check",),
    )
    check = FunctionModel(
        name="check", visibility="internal", modifiers=(), writes=(),
        external_calls=(), line=8,
        parameters=(ParameterModel("data", "Data", "calldata"),),
        execution_predicates=("registry[data.key] == data.endpoint",),
    )
    register = FunctionModel(
        name="register", visibility="external", modifiers=(), writes=("registry",),
        external_calls=(), line=11,
        parameters=(
            ParameterModel("key", "uint256"),
            ParameterModel("endpoint", "address"),
        ),
    )
    contract = ContractModel(
        "Callback", str(source), (execute, check, register),
        pragma="^0.8.20", state_variables=("registry",),
    )
    rendered, functions = _state_setup_source(contract, execute, "cydraCallbackInput")
    assert functions == ("register",)
    assert "target.register(cydraCallbackInput.key, cydraCallbackInput.endpoint);" in rendered


def test_callback_runtime_generator_materializes_state_backed_constructor_interface_stub(tmp_path: Path):
    interface = tmp_path / "IHelper.sol"
    interface.write_text(
        """
        interface IHelper {
            function performChecks(uint256 value) external view returns (uint256[] memory);
            function performSideEffects(uint256 value) external;
        }
        """,
        encoding="utf-8",
    )
    source = tmp_path / "Callback.sol"
    source.write_text(
        """
        pragma solidity ^0.8.20;
        import "./IHelper.sol";
        contract Callback {
            IHelper public helper;
            constructor(address helperAddress) {
                helper = IHelper(helperAddress);
            }
            function execute(uint256 amount) external {
                helper.performChecks(amount);
                helper.performSideEffects(amount);
            }
        }
        """,
        encoding="utf-8",
    )
    function = FunctionModel(
        name="execute",
        visibility="external",
        modifiers=(),
        writes=(),
        external_calls=(("helper", "performChecks"), ("helper", "performSideEffects")),
        line=8,
        parameters=(ParameterModel("amount", "uint256"),),
    )
    from cydra.models import ConstructorModel
    contract = ContractModel(
        "Callback",
        str(source),
        (function,),
        pragma="^0.8.20",
        constructor=ConstructorModel(
            (ParameterModel("helperAddress", "address"),), 4
        ),
    )
    hypothesis = Hypothesis(
        "H-CALLBACK-STATE-ORDER-execute", "claim",
        "INV-CALLBACK-STATE-ORDER-execute", "execute",
        "callback", "impact",
    )
    experiment = Experiment(
        "X-H-CALLBACK-STATE-ORDER-execute", hypothesis.hypothesis_id,
        "reenter", (), 2.0, planned_inputs=("1",), target_function="execute",
    )
    output = tmp_path / "test" / "generated.t.sol"
    generate_callback_state_order_test(
        hypothesis, experiment, str(source), "Callback", output, contract
    )
    rendered = output.read_text(encoding="utf-8")
    assert "contract CydraIHelperStub" in rendered
    assert "IHelper internal helperStub" not in rendered
    assert "helperStub = new CydraIHelperStub();" in rendered
    assert "new Callback(address(helperStub))" in rendered
    assert "function performChecks(uint256 value) external view returns (uint256[] memory)" in rendered


def test_callback_caller_binding_can_target_non_first_parameter():
    from cydra.callback_state_order_execution import _caller_bound_parameter_paths

    source = Path("/tmp/Callback.sol")
    function = FunctionModel(
        name="execute",
        visibility="external",
        modifiers=(),
        writes=(),
        external_calls=(),
        line=1,
        parameters=(
            ParameterModel("proof", "uint256"),
            ParameterModel("data", "Data"),
        ),
    )
    check = FunctionModel(
        name="check",
        visibility="internal",
        modifiers=(),
        writes=(),
        external_calls=(),
        line=2,
        parameters=(ParameterModel("data", "Data"),),
        execution_predicates=("data.endpoint == msg.sender",),
    )
    contract = ContractModel(
        "Callback",
        str(source),
        (function, check),
        pragma="^0.8.20",
    )
    source.write_text(
        "pragma solidity ^0.8.20; contract Callback { "
        "function execute(uint256 proof, Data calldata data) external { check(data); } "
        "function check(Data calldata data) internal { require(data.endpoint == msg.sender); } "
        "struct Data { address endpoint; } }",
        encoding="utf-8",
    )
    assert _caller_bound_parameter_paths(contract, function) == ("data.endpoint",)


def test_legacy_callback_renderer_materializes_unreferenced_structured_planned_identifier(tmp_path: Path):
    source = tmp_path / "Callback.sol"
    source.write_text(
        """
        pragma solidity ^0.8.20;
        contract Callback {
            struct Data { uint256 key; address endpoint; }
            function execute(Data calldata data) external {
                (bool ok,) = msg.sender.call("");
                require(ok);
            }
        }
        """,
        encoding="utf-8",
    )
    from cydra.solidity_model import parse_solidity
    contract = next(item for item in parse_solidity(source) if item.name == "Callback")
    hypothesis = Hypothesis(
        "H-CALLBACK-STATE-ORDER-execute", "claim",
        "INV-CALLBACK-STATE-ORDER-execute", "execute", "callback", "impact",
    )
    experiment = Experiment(
        "X-H-CALLBACK-STATE-ORDER-execute", hypothesis.hypothesis_id,
        "reenter", (), 2.0,
        planned_inputs=(" (0, address(0)) ",),
        target_function="execute",
    )
    output = tmp_path / "test" / "generated.t.sol"
    generate_callback_state_order_test(
        hypothesis, experiment, str(source), "Callback", output, contract,
    )
    rendered = output.read_text(encoding="utf-8")
    assert "Data memory cydra_data = (0, address(0));" in rendered
    assert "abi.encodeCall(target.execute, (cydra_data))" in rendered


def test_legacy_callback_renderer_materializes_target_derived_state_setup_and_caller_binding(tmp_path: Path):
    source = tmp_path / "Callback.sol"
    source.write_text(
        """
        pragma solidity ^0.8.20;
        contract Callback {
            mapping(uint256 => address) registry;
            struct Data { uint256 key; address endpoint; }
            function execute(uint256 proof, Data calldata data) external {
                check(data);
            }
            function check(Data calldata data) internal {
                require(data.endpoint == msg.sender);
                require(registry[data.key] == data.endpoint);
                (bool ok,) = msg.sender.call("");
                require(ok);
            }
            function register(uint256 key, address endpoint) external {
                registry[key] = endpoint;
            }
        }
        """,
        encoding="utf-8",
    )
    from cydra.solidity_model import parse_solidity
    contract = next(item for item in parse_solidity(source) if item.name == "Callback")
    hypothesis = Hypothesis(
        "H-CALLBACK-STATE-ORDER-execute", "claim",
        "INV-CALLBACK-STATE-ORDER-execute", "execute", "callback", "impact",
    )
    experiment = Experiment(
        "X-H-CALLBACK-STATE-ORDER-execute", hypothesis.hypothesis_id,
        "reenter", (), 2.0,
        planned_inputs=("1", "(0, address(0))"),
        target_function="execute",
    )
    output = tmp_path / "test" / "generated.t.sol"
    generate_callback_state_order_test(
        hypothesis, experiment, str(source), "Callback", output, contract,
    )
    rendered = output.read_text(encoding="utf-8")
    assert "cydra_data.endpoint = address(attacker);" in rendered
    assert "target.register(cydra_data.key, cydra_data.endpoint);" in rendered
    assert "abi.encodeCall(target.execute, (1, cydra_data))" in rendered
    assert "target.register(cydra_data.key, cydra_data.endpoint);" in rendered
    assert "cydra_circomData" not in rendered



def test_callback_state_setup_resolves_role_address_through_readiness_module(tmp_path, monkeypatch):
    from cydra.callback_state_order_execution import _state_setup_source
    from cydra.execution_readiness import SetupAction

    source = tmp_path / "Callback.sol"
    source.write_text(
        "pragma solidity ^0.8.20; contract Callback { "
        "mapping(uint256 => address) registry; "
        "function execute(Data calldata data) external {} "
        "function register(uint256 key, address endpoint) external { registry[key] = endpoint; } "
        "struct Data { uint256 key; address endpoint; } }",
        encoding="utf-8",
    )
    execute = FunctionModel(
        "execute", "external", (), (), (), 1,
        parameters=(ParameterModel("data", "Data", "calldata"),),
    )
    register = FunctionModel(
        "register", "external", (), ("registry",), (), 1,
        parameters=(ParameterModel("key", "uint256"), ParameterModel("endpoint", "address")),
    )
    contract = ContractModel(
        "Callback", str(source), (execute, register), pragma="^0.8.20",
        state_variables=("registry",),
    )
    monkeypatch.setattr(
        "cydra.callback_state_order_execution.constructible_state_setup_plan",
        lambda *args, **kwargs: (SetupAction("register", "admin", ("execute", "registry")),),
    )
    monkeypatch.setattr(
        "cydra.callback_state_order_execution.execution_readiness.role_address_expression",
        lambda role: "address(0x1002)" if role == "admin" else None,
    )
    monkeypatch.setattr(
        "cydra.callback_state_order_execution._state_setup_argument_vector",
        lambda *args, **kwargs: ("cydraCallbackInput.key", "cydraCallbackInput.endpoint"),
    )
    rendered, functions = _state_setup_source(contract, execute, "cydraCallbackInput")
    assert functions == ("register",)
    assert "vm.startPrank(address(0x1002));" in rendered
    assert "target.register(cydraCallbackInput.key, cydraCallbackInput.endpoint);" in rendered
    assert "vm.stopPrank();" in rendered
