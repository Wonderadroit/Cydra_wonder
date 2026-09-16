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


def _experiment(inputs=()):
    return Experiment(
        experiment_id="X-H-AUTH-withdraw",
        hypothesis_id="H-AUTH-withdraw",
        action="call withdraw",
        discriminates=("authorization",),
        cost=1.0,
        planned_inputs=tuple(inputs),
    )


def test_planned_inputs_are_authoritative_for_target_call():
    function = _function("withdraw", (ParameterModel("amount", "uint256"),))
    assert render_function_call(_experiment(("1",)), function) == "target.withdraw(1);"


def test_planned_input_vector_is_function_scoped_by_the_caller():
    withdraw = _function("withdraw", (ParameterModel("amount", "uint256"),))
    deposit = _function("deposit", (ParameterModel("amount", "uint256"),))
    experiment = _experiment(("1",))
    assert render_function_call(experiment, withdraw) == "target.withdraw(1);"
    assert render_function_call(experiment, deposit) == "target.deposit(1);"


def test_empty_plan_preserves_conservative_fallback():
    function = _function("withdraw", (ParameterModel("amount", "uint256"), ParameterModel("recipient", "address")))
    assert render_function_call(_experiment(), function) == "target.withdraw(1, address(0xCAFE));"


def test_partial_plan_cannot_silently_reorder_or_invent_arguments():
    function = _function("withdraw", (
        ParameterModel("amount", "uint256"),
        ParameterModel("recipient", "address"),
    ))
    with pytest.raises(ValueError, match="planned input arity mismatch"):
        render_function_call(_experiment(("1",)), function)
