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
