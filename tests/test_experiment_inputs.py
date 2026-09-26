from cydra.compiler_constraints import ConstraintEvidence
from cydra.constraint_candidates import select_parameter_candidates
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


def test_compatible_nonnegative_and_positive_constraints_use_one():
    parameters = (ParameterModel(name="amount", type="uint256"),)
    result = plan_parameter_inputs(
        parameters,
        (
            evidence("amount", 0, "amount >= 0"),
            evidence("amount", 0, "amount > 0"),
        ),
        {"amount": "0"},
        function_name="withdraw",
    )
    assert result == ("1",)


def test_nonzero_integer_constraint_uses_one():
    parameters = (ParameterModel(name="amount", type="uint256"),)
    result = plan_parameter_inputs(
        parameters,
        (evidence("amount", 0, "amount != 0"),),
        {"amount": "0"},
        function_name="withdraw",
    )
    assert result == ("1",)


def test_integer_equality_constraint_uses_observed_value():
    parameters = (ParameterModel(name="amount", type="uint256"),)
    result = plan_parameter_inputs(
        parameters,
        (evidence("amount", 0, "amount == 7"),),
        {"amount": "0"},
        function_name="withdraw",
    )
    assert result == ("7",)


def test_contradictory_zero_and_positive_constraints_fail_closed():
    parameters = (ParameterModel(name="amount", type="uint256"),)
    result = plan_parameter_inputs(
        parameters,
        (
            evidence("amount", 0, "amount == 0"),
            evidence("amount", 0, "amount > 0"),
        ),
        {"amount": "0"},
        function_name="withdraw",
    )
    assert result == ("0",)


def test_fixed_bytes_defaults_preserve_declared_width():
    from cydra.experiment_inputs import conservative_defaults
    parameters = (
        ParameterModel(name="referrer", type="bytes3"),
        ParameterModel(name="digest", type="bytes32"),
    )
    defaults = conservative_defaults(parameters)
    assert defaults == {
        "referrer": 'bytes3(hex"010000")',
        "digest": 'bytes32(hex"0100000000000000000000000000000000000000000000000000000000000000")',
    }


def test_revert_guard_zero_requires_nonzero_execution_value():
    parameters = (ParameterModel(name="amount", type="uint256"),)
    result = plan_parameter_inputs(
        parameters,
        (
            ConstraintEvidence(
                "Target", "borrow", "amount", 0, "amount == 0",
                "solc-json-ast:Target.sol", kind="revert_guard"
            ),
        ),
        {"amount": "0"},
        function_name="borrow",
    )
    assert result == ("1",)


def test_revert_guard_nonzero_address_allows_zero_address():
    parameters = (ParameterModel(name="account", type="address"),)
    result = plan_parameter_inputs(
        parameters,
        (
            ConstraintEvidence(
                "Target", "close", "account", 0, "account != 0",
                "solc-json-ast:Target.sol", kind="revert_guard"
            ),
        ),
        {"account": "address(0xCAFE)"},
        function_name="close",
    )
    assert result == ("address(0)",)


def test_revert_guard_collection_bound_selects_zero_index():
    parameters = (ParameterModel("index", "uint256"),)
    constraints = (
        ConstraintEvidence(
            contract="Target",
            function="setItem",
            parameter="index",
            parameter_index=0,
            predicate="index >= items.length",
            source="solc-json-ast:test",
            kind="revert_guard",
        ),
    )
    candidates = select_parameter_candidates(parameters, constraints, function_name="setItem")
    assert candidates[0].value == "0"


def test_structured_defaults_render_source_defined_structs(tmp_path):
    from cydra.experiment_inputs import plan_parameter_inputs
    from cydra.models import ContractModel

    source = tmp_path / "Target.sol"
    source.write_text(
        """
        pragma solidity ^0.8.20;
        contract Target {
            struct Action {
                address recipient;
                uint256 amount;
                bytes payload;
            }
            function execute(Action calldata action, int256[] calldata deltas) external {}
        }
        """,
        encoding="utf-8",
    )
    model = ContractModel(
        name="Target",
        source=str(source),
        functions=(),
    )
    parameters = (
        ParameterModel(name="action", type="Action"),
        ParameterModel(name="deltas", type="int256[]"),
    )
    result = plan_parameter_inputs(
        parameters,
        (),
        function_name="execute",
        contract_model=model,
    )
    assert result == (
        '(address(0xCAFE), 1, bytes(""))',
        "new int256[](0)",
    )


def test_structured_defaults_resolve_imported_structs(tmp_path):
    from cydra.experiment_inputs import plan_parameter_inputs
    from cydra.models import ContractModel

    (tmp_path / "foundry.toml").write_text("[profile.default]\n", encoding="utf-8")
    types = tmp_path / "Types.sol"
    types.write_text(
        """
        pragma solidity ^0.8.20;
        struct Action {
            address recipient;
            uint256 amount;
            bytes payload;
        }
        """,
        encoding="utf-8",
    )
    source = tmp_path / "Target.sol"
    source.write_text(
        """
        pragma solidity ^0.8.20;
        import {Action} from "./Types.sol";
        contract Target {
            function execute(Action calldata action) external {}
        }
        """,
        encoding="utf-8",
    )
    model = ContractModel(name="Target", source=str(source), functions=())
    result = plan_parameter_inputs(
        (ParameterModel(name="action", type="Action"),),
        (),
        function_name="execute",
        contract_model=model,
    )
    assert result == ('(address(0xCAFE), 1, bytes(""))',)
