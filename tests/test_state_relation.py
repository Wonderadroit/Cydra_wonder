from pathlib import Path

from cydra.models import ContractModel, FunctionModel
from cydra.state_relation import plan_source_state_relations


def test_literal_compound_state_transition_is_source_backed(tmp_path: Path):
    source = tmp_path / "Target.sol"
    source.write_text(
        "contract Target { uint256 public counter; "
        "function step() external { counter += 1; } }",
        encoding="utf-8",
    )
    model = ContractModel(
        "Target", str(source),
        (FunctionModel("step", "external", (), ("counter",), (), 1),),
        state_variables=("counter",),
    )
    relations = plan_source_state_relations(model, model.functions[0])
    assert [item.expression for item in relations] == [
        "after(counter) == before(counter) + 1"
    ]


def test_dynamic_state_transition_fails_closed(tmp_path: Path):
    source = tmp_path / "Target.sol"
    source.write_text(
        "contract Target { uint256 public counter; "
        "function step(uint256 amount) external { counter += amount; } }",
        encoding="utf-8",
    )
    model = ContractModel(
        "Target", str(source),
        (FunctionModel("step", "external", (), ("counter",), (), 1),),
        state_variables=("counter",),
    )
    assert plan_source_state_relations(model, model.functions[0]) == ()
