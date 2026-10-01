from cydra.sequence_foundry import _coerce_struct_constructor_to_tuple


def test_typed_struct_constructor_is_normalized_to_tuple():
    assert _coerce_struct_constructor_to_tuple("FeeStructure(address(0xCAFE), 1, 2)", "FeeStructure") == "(address(0xCAFE), 1, 2)"


def test_existing_tuple_is_preserved():
    value = "(address(0xCAFE), (1, 2), bytes(\"\"))"
    assert _coerce_struct_constructor_to_tuple(value, "FeeStructure") == value


def test_non_struct_expression_is_unchanged():
    value = "abi.decode(blob, (FeeStructure))"
    assert _coerce_struct_constructor_to_tuple(value, "FeeStructure") == value



def test_setup_argument_materializes_complete_struct_from_source(tmp_path):
    from cydra.models import ContractModel, FunctionModel, ParameterModel
    from scripts.run_benchmark_blind import _setup_argument

    source = tmp_path / "Target.sol"
    source.write_text(
        """contract Target {
            struct FeeStructure {
                address feeToken;
                uint256 flatFee;
                uint256 variableRate;
            }
            function seed(FeeStructure memory fees) external {}
        }\n""",
        encoding="utf-8",
    )
    function = FunctionModel(
        "seed", "external", (), (), (), 1,
        parameters=(ParameterModel("fees", "FeeStructure"),),
    )
    contract = ContractModel("Target", str(source), (function,))

    assert _setup_argument(function, 0, None, contract) == (
        "FeeStructure({ feeToken: address(0), flatFee: 0, variableRate: 0 })"
    )
