from pathlib import Path

from cydra.internal_call_effects import effective_writes
from cydra.models import ContractModel, FunctionModel
from cydra.solidity_model import parse_solidity
from cydra.solidity_system_model import project_contracts


def test_parser_resolves_direct_internal_calls_and_transitive_writes(tmp_path: Path):
    path = tmp_path / "Target.sol"
    path.write_text(
        "contract Target {\n"
        "    uint256 public counter;\n"
        "    function helper() internal { counter += 1; }\n"
        "    function entry() external { helper(); }\n"
        "    function qualified() external { this.helper(); }\n"
        "}\n",
        encoding="utf-8",
    )
    contract = parse_solidity(path)[0]
    functions = {item.name: item for item in contract.functions}

    assert functions["entry"].internal_calls == ("helper",)
    assert functions["helper"].internal_calls == ()
    assert functions["qualified"].internal_calls == ()
    assert functions["entry"].writes == ()
    assert functions["helper"].writes == ("counter",)
    assert effective_writes(contract, functions["entry"]) == ("counter",)


def test_internal_effect_composition_terminates_on_cycles():
    a = FunctionModel("a", "internal", (), (), (), 1, internal_calls=("b",))
    b = FunctionModel("b", "internal", (), ("counter",), (), 2, internal_calls=("a",))
    contract = ContractModel("Target", "Target.sol", (a, b), state_variables=("counter",))

    assert effective_writes(contract, a) == ("counter",)
    assert effective_writes(contract, b) == ("counter",)


def test_system_projection_records_internal_call_and_composed_write():
    helper = FunctionModel("helper", "internal", (), ("counter",), (), 2)
    entry = FunctionModel("entry", "external", (), (), (), 3, internal_calls=("helper",))
    contract = ContractModel("Target", "Target.sol", (helper, entry), state_variables=("counter",))

    model = project_contracts((contract,))
    entry_id = "function:Target.sol:Target:entry()"
    helper_id = "function:Target.sol:Target:helper()"
    state_id = "state:Target.sol:Target:counter"

    assert any(e.source == entry_id and e.relation == "internal_call" and e.target == helper_id for e in model.edges)
    assert any(e.source == entry_id and e.relation == "writes" and e.target == state_id for e in model.edges)