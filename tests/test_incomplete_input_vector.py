from cydra.compiler_constraints import ConstraintEvidence
from cydra.experiment_inputs import plan_parameter_inputs
from cydra.models import ParameterModel


def test_incomplete_custom_struct_vector_fails_closed():
    parameters = (
        ParameterModel(name="helper", type="UnknownHelper"),
        ParameterModel(name="amount", type="uint256"),
    )
    result = plan_parameter_inputs(
        parameters,
        (),
        {"amount": "1"},
        function_name="initialize",
    )
    assert result == ()


def test_complete_primitive_vector_is_preserved():
    parameters = (
        ParameterModel(name="recipient", type="address"),
        ParameterModel(name="amount", type="uint256"),
    )
    result = plan_parameter_inputs(
        parameters,
        (),
        {"recipient": "address(0xBEEF)", "amount": "1"},
        function_name="initialize",
    )
    assert result == ("address(0xBEEF)", "1")
