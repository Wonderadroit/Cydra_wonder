from types import SimpleNamespace

from cydra.callback_state_order_execution import _select_structured_binding_name


def test_structured_binding_selection_does_not_match_prefix():
    function = SimpleNamespace(
        parameters=(
            SimpleNamespace(name="c"),
            SimpleNamespace(name="circomData"),
        )
    )
    rendered_arguments = {"c": "0", "circomData": "cydra_circomData"}
    parameter_setup = "CircomData memory cydra_circomData = (1, 1);"

    assert _select_structured_binding_name(
        function, rendered_arguments, parameter_setup
    ) == "cydra_circomData"
