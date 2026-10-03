from cydra.sequence_foundry import _coerce_struct_constructor_to_tuple, generate_sequence_test_from_experiment


def test_typed_struct_constructor_is_normalized_to_tuple():
    assert _coerce_struct_constructor_to_tuple("FeeStructure(address(0xCAFE), 1, 2)", "FeeStructure") == "(address(0xCAFE), 1, 2)"


def test_existing_tuple_is_preserved():
    value = "(address(0xCAFE), (1, 2), bytes(\"\"))"
    assert _coerce_struct_constructor_to_tuple(value, "FeeStructure") == value


def test_non_struct_expression_is_unchanged():
    value = "abi.decode(blob, (FeeStructure))"
    assert _coerce_struct_constructor_to_tuple(value, "FeeStructure") == value



def test_named_struct_constructor_is_reordered_by_source_fields(tmp_path):
    from pathlib import Path
    from cydra.models import ContractModel, Experiment, ExperimentStep, FunctionModel, Hypothesis, ParameterModel

    root = Path(__file__).parent / "_tmp_named_struct"
    root.mkdir(exist_ok=True)
    (root / "foundry.toml").write_text("[profile.default]\\n", encoding="utf-8")
    (root / "types").mkdir(exist_ok=True)
    (root / "types" / "Fee.sol").write_text(
        "struct FeeStructure { address feeToken; uint256 flatFee; uint256 variableRate; }\\n",
        encoding="utf-8",
    )
    source = root / "Target.sol"
    source.write_text(
        'pragma solidity ^0.8.20; import { FeeStructure } from "./types/Fee.sol"; '
        "contract Target { uint256 public fee; "
        "function transact(FeeStructure calldata data) external { require(data.flatFee == fee); } }",
        encoding="utf-8",
    )
    model = ContractModel(
        "Target", str(source),
        (FunctionModel(
            "transact", "external", (), (), (), 3,
            parameters=(ParameterModel("data", "FeeStructure", "calldata"),),
            execution_predicates=("data.flatFee == fee",),
            execution_predicate_polarities=(("data.flatFee == fee", "must_hold"),),
        ),),
    )
    hypothesis = Hypothesis("H-NAMED-STRUCT", "candidate", "INV-NAMED-STRUCT", "transact", "attacker", "candidate")
    experiment = Experiment(
        "X-NAMED-STRUCT", hypothesis.hypothesis_id, "observe", ("violation",), 1.0,
        planned_inputs=("FeeStructure({ variableRate: 2, feeToken: address(0xCAFE), flatFee: 1 })",),
        target_function="transact", steps=(ExperimentStep("transact", ()),),
    )
    generated = generate_sequence_test_from_experiment(
        hypothesis, experiment, "../Target.sol", "Target", root / "test" / "generated.t.sol", model,
        verify_state_prerequisites=True, stop_before_target=True,
    )
    rendered = generated.read_text(encoding="utf-8")
    assert "FeeStructure(address(0xCAFE), 1, 2)" in rendered
    assert "target.transact(" not in rendered
