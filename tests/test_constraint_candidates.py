from cydra.compiler_constraints import ConstraintEvidence
from cydra.constraint_candidates import select_parameter_candidates
from cydra.models import ParameterModel


def constraint(parameter, index, predicate, source="solc-json-ast:Target.sol"):
    return ConstraintEvidence(
        contract="Target",
        function="arbitraryFunction",
        parameter=parameter,
        parameter_index=index,
        predicate=predicate,
        source=source,
    )


def test_numeric_precondition_selects_minimal_satisfying_value():
    parameters = (ParameterModel(name="amount", type="uint256"),)
    result = select_parameter_candidates(parameters, (constraint("amount", 0, "amount > 0"),))
    assert result[0].value == "1"
    assert result[0].parameter == "amount"


def test_address_nonzero_precondition_selects_nonzero_value():
    parameters = (ParameterModel(name="recipient", type="address"),)
    result = select_parameter_candidates(parameters, (constraint("recipient", 0, "recipient != address(0)"),))
    assert result[0].value == "address(0xCAFE)"


def test_unrelated_guard_is_not_used():
    parameters = (ParameterModel(name="amount", type="uint256"),)
    result = select_parameter_candidates(parameters, (constraint("other", 0, "other > 0"),))
    assert result == ()


def test_multiple_parameters_do_not_cross_contaminate():
    parameters = (
        ParameterModel(name="recipient", type="address"),
        ParameterModel(name="amount", type="uint256"),
    )
    constraints = (
        constraint("recipient", 0, "recipient != address(0)"),
        constraint("amount", 1, "amount > 0"),
    )
    result = select_parameter_candidates(parameters, constraints)
    assert [(item.parameter, item.parameter_index, item.value) for item in result] == [
        ("recipient", 0, "address(0xCAFE)"),
        ("amount", 1, "1"),
    ]


def test_unrecognized_predicate_preserves_fallback_by_omitting_candidate():
    parameters = (ParameterModel(name="amount", type="uint256"),)
    result = select_parameter_candidates(parameters, (constraint("amount", 0, "amount <= maxAmount"),))
    assert result == ()


def test_constraint_is_not_class_specific():
    parameters = (ParameterModel(name="amount", type="uint256"),)
    evidence = constraint("amount", 0, "amount > 0")
    evidence = ConstraintEvidence(**{**evidence.__dict__, "function": "withdraw"})
    result = select_parameter_candidates(parameters, (evidence,))
    assert result[0].parameter == "amount"
    assert result[0].value == "1"
