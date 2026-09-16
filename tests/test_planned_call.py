import pytest

from cydra.models import Experiment, FunctionModel, ParameterModel
from cydra.planned_call import render_function_call


def _function(name="withdraw", parameters=()):
    return FunctionModel(
        name=name,
        visibility="external",
        modifiers=(),
        writes=("balances",),
        external_calls=(),
        line=1,
        parameters=tuple(parameters),
    )


def _experiment(inputs=(), target_function=None, experiment_id="X-H-AUTH-withdraw", hypothesis_id="H-AUTH-withdraw"):
    return Experiment(
        experiment_id=experiment_id,
        hypothesis_id=hypothesis_id,
        action="call target function",
        discriminates=("candidate behavior",),
        cost=1.0,
        planned_inputs=tuple(inputs),
        target_function=target_function,
    )


def test_planned_inputs_are_authoritative_for_target_call():
    function = _function("withdraw", (ParameterModel("amount", "uint256"),))
    assert render_function_call(_experiment(("1",), "withdraw"), function) == "target.withdraw(1);"


def test_target_identity_prevents_cross_function_plan_reuse():
    withdraw = _function("withdraw", (ParameterModel("amount", "uint256"),))
    deposit = _function("deposit", (ParameterModel("amount", "uint256"),))
    experiment = _experiment(("1",), "withdraw")
    assert render_function_call(experiment, withdraw) == "target.withdraw(1);"
    with pytest.raises(ValueError, match="experiment target mismatch"):
        render_function_call(experiment, deposit)


def test_legacy_unbound_experiment_can_render_for_compatible_function():
    function = _function("withdraw", (ParameterModel("amount", "uint256"),))
    assert render_function_call(_experiment(("1",)), function) == "target.withdraw(1);"


def test_empty_plan_preserves_conservative_fallback():
    function = _function("withdraw", (ParameterModel("amount", "uint256"), ParameterModel("recipient", "address")))
    assert render_function_call(_experiment(), function) == "target.withdraw(1, address(0xCAFE));"


def test_empty_plan_uses_the_same_canonical_defaults_for_multiple_types():
    function = _function(
        "configure",
        (
            ParameterModel("who", "address payable"),
            ParameterModel("enabled", "bool"),
            ParameterModel("label", "string"),
            ParameterModel("payload", "bytes32"),
        ),
    )
    assert render_function_call(_experiment(), function) == (
        'target.configure(payable(address(0xCAFE)), false, "CYDRA", bytes32(0x01));'
    )


def test_unsupported_custom_type_fails_closed_without_fabricating_argument():
    function = _function("configure", (ParameterModel("settings", "Settings"),))
    with pytest.raises(ValueError, match="unsupported planned-call argument type"):
        render_function_call(_experiment(), function)


def test_partial_plan_cannot_silently_reorder_or_invent_arguments():
    function = _function("withdraw", (
        ParameterModel("amount", "uint256"),
        ParameterModel("recipient", "address"),
    ))
    with pytest.raises(ValueError, match="planned input arity mismatch"):
        render_function_call(_experiment(("1",)), function)


def test_planned_call_does_not_depend_on_vulnerability_class_or_invariant_id():
    function = _function("rebalance", (ParameterModel("amount", "uint256"),))
    experiment = _experiment(
        ("777",),
        "rebalance",
        experiment_id="X-HYPOTHESIS-rebalance",
        hypothesis_id="HYPOTHESIS-rebalance",
    )
    assert render_function_call(experiment, function) == "target.rebalance(777);"
