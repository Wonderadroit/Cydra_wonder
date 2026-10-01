from cydra.sequence_foundry import _coerce_struct_constructor_to_tuple


def test_typed_struct_constructor_is_normalized_to_tuple():
    assert _coerce_struct_constructor_to_tuple("FeeStructure(address(0xCAFE), 1, 2)") == "(address(0xCAFE), 1, 2)"


def test_existing_tuple_is_preserved():
    value = "(address(0xCAFE), (1, 2), bytes(\"\"))"
    assert _coerce_struct_constructor_to_tuple(value) == value


def test_non_struct_expression_is_unchanged():
    value = "abi.decode(blob, (FeeStructure))"
    assert _coerce_struct_constructor_to_tuple(value) == value
