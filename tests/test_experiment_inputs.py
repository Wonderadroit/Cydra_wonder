from cydra.compiler_constraints import ConstraintEvidence
from cydra.experiment_inputs import plan_parameter_inputs
from cydra.models import ParameterModel


def evidence(parameter, index, predicate, function="withdraw"):
    return ConstraintEvidence(
        contract="Target",
        function=function,
        parameter=parameter,
        parameter_index=index,
        predicate=predicate,
        source="solc-json-ast:contracts/Target.sol",
    )


def test_constraint_overrides_only_constrained_parameter():
    parameters = (
        ParameterModel(name="recipient", type="address"),
        ParameterModel(name="amount", type="uint256"),
        ParameterModel(name="flag", type="bool"),
    )
    defaults = {"recipient": "address(0)", "amount": "0", "flag": "false"}
    result = plan_parameter_inputs(
        parameters,
        (evidence("amount", 1, "amount > 0"),),
        defaults,
        function_name="withdraw",
    )
    assert result == ("address(0)", "1", "false")


def test_constraints_are_function_local_and_parameter_local():
    parameters = (
        ParameterModel(name="recipient", type="address"),
        ParameterModel(name="amount", type="uint256"),
    )
    defaults = {"recipient": "address(0)", "amount": "0"}
    result = plan_parameter_inputs(
        parameters,
        (
            evidence("amount", 1, "amount > 0", function="withdraw"),
            evidence("amount", 1, "amount > 0", function="deposit"),
            evidence("other", 0, "other > 0", function="withdraw"),
        ),
        defaults,
        function_name="withdraw",
    )
    assert result == ("address(0)", "1")


def test_foreign_function_constraint_cannot_change_target_input():
    parameters = (ParameterModel(name="amount", type="uint256"),)
    result = plan_parameter_inputs(
        parameters,
        (evidence("amount", 0, "amount > 0", function="deposit"),),
        {"amount": "0"},
        function_name="withdraw",
    )
    assert result == ("0",)


def test_unknown_constraint_keeps_conservative_default():
    parameters = (ParameterModel(name="amount", type="uint256"),)
    result = plan_parameter_inputs(
        parameters,
        (evidence("amount", 0, "amount <= maxAmount"),),
        {"amount": "0"},
        function_name="withdraw",
    )
    assert result == ("0",)
