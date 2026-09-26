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
    assert 'abi.encodeWithSignature("execute(uint256)", 1)' in rendered


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
