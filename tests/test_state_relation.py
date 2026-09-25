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


def test_relation_is_scoped_to_selected_function(tmp_path: Path):
    source = tmp_path / "Target.sol"
    source.write_text(
        "contract Target { uint256 public counter; "
        "function step() external { counter += 1; } "
        "function other() external { counter += 2; } }",
        encoding="utf-8",
    )
    model = ContractModel(
        "Target", str(source),
        (
            FunctionModel("step", "external", (), ("counter",), (), 1),
            FunctionModel("other", "external", (), ("counter",), (), 1),
        ),
        state_variables=("counter",),
    )
    assert [item.expression for item in plan_source_state_relations(model, model.functions[0])] == [
        "after(counter) == before(counter) + 1"
    ]


def test_keyed_literal_compound_state_transition_is_source_backed(tmp_path: Path):
    source = tmp_path / "Target.sol"
    source.write_text(
        "contract Target { mapping(address => mapping(uint256 => uint256)) public queued; "
        "function execute(address user, uint256 epoch) external { queued[user][epoch] += 1; } }",
        encoding="utf-8",
    )
    from cydra.models import ParameterModel
    model = ContractModel(
        "Target", str(source),
        (
            FunctionModel(
                "execute", "external", (), ("queued",), (), 1,
                parameters=(ParameterModel("user", "address"), ParameterModel("epoch", "uint256")),
            ),
        ),
        state_variables=("queued",),
    )
    relations = plan_source_state_relations(model, model.functions[0])
    assert len(relations) == 1
    assert relations[0].index_expressions == ("user", "epoch")
    assert relations[0].expression == "after(queued[user][epoch]) == before(queued[user][epoch]) + 1"


def test_parameter_compound_state_transition_is_source_backed(tmp_path: Path):
    source = tmp_path / "Target.sol"
    source.write_text(
        "contract Target { uint256 public counter; "
        "function step(uint256 amount) external { counter += amount; } }",
        encoding="utf-8",
    )
    from cydra.models import ParameterModel
    model = ContractModel(
        "Target", str(source),
        (
            FunctionModel(
                "step", "external", (), ("counter",), (), 2,
                parameters=(ParameterModel("amount", "uint256"),),
            ),
        ),
        state_variables=("counter",),
    )
    relations = plan_source_state_relations(model, model.functions[0])
    assert len(relations) == 1
    assert relations[0].rhs_expression == "amount"
    assert relations[0].expression == "after(counter) == before(counter) + amount"


def test_non_parameter_compound_state_transition_fails_closed(tmp_path: Path):
    source = tmp_path / "Target.sol"
    source.write_text(
        "contract Target { uint256 public counter; "
        "function step(uint256 amount) external { uint256 delta = amount + 1; counter += delta; } }",
        encoding="utf-8",
    )
    from cydra.models import ParameterModel
    model = ContractModel(
        "Target", str(source),
        (
            FunctionModel(
                "step", "external", (), ("counter",), (), 2,
                parameters=(ParameterModel("amount", "uint256"),),
            ),
        ),
        state_variables=("counter",),
    )
    assert plan_source_state_relations(model, model.functions[0]) == ()


def test_caller_and_state_indexes_are_source_backed(tmp_path: Path):
    source = tmp_path / "Target.sol"
    source.write_text(
        "contract Target { "
        "uint128 public depositEpoch; "
        "mapping(address => mapping(uint256 => uint128)) public queuedDeposit; "
        "function requestDeposit(uint128 assets) external { "
        "queuedDeposit[msg.sender][depositEpoch] += assets; } }",
        encoding="utf-8",
    )
    from cydra.models import ParameterModel
    model = ContractModel(
        "Target", str(source),
        (
            FunctionModel(
                "requestDeposit", "external", (), ("queuedDeposit",), (), 4,
                parameters=(ParameterModel("assets", "uint128"),),
            ),
        ),
        state_variables=("depositEpoch", "queuedDeposit"),
    )
    relations = plan_source_state_relations(model, model.functions[0])
    assert len(relations) == 1
    assert relations[0].index_expressions == ("msg.sender", "depositEpoch")
    assert relations[0].rhs_expression == "assets"


def test_direct_self_referential_scalar_assignment_is_source_backed(tmp_path: Path):
    source = tmp_path / "Target.sol"
    source.write_text(
        "contract Target { uint256 public counter; "
        "function step(uint256 amount) external { counter = counter + amount; } }",
        encoding="utf-8",
    )
    from cydra.models import ParameterModel
    model = ContractModel(
        "Target", str(source),
        (
            FunctionModel(
                "step", "external", (), ("counter",), (), 1,
                parameters=(ParameterModel("amount", "uint256"),),
            ),
        ),
        state_variables=("counter",),
    )
    relations = plan_source_state_relations(model, model.functions[0])
    assert len(relations) == 1
    assert relations[0].expression == "after(counter) == before(counter) + amount"


def test_direct_self_referential_scalar_subtraction_is_source_backed(tmp_path: Path):
    source = tmp_path / "Target.sol"
    source.write_text(
        "contract Target { uint256 public counter; "
        "function step(uint256 amount) external { counter = counter - amount; } }",
        encoding="utf-8",
    )
    from cydra.models import ParameterModel
    model = ContractModel(
        "Target", str(source),
        (
            FunctionModel(
                "step", "external", (), ("counter",), (), 1,
                parameters=(ParameterModel("amount", "uint256"),),
            ),
        ),
        state_variables=("counter",),
    )
    relations = plan_source_state_relations(model, model.functions[0])
    assert len(relations) == 1
    assert relations[0].expression == "after(counter) == before(counter) - amount"


def test_direct_self_referential_keyed_assignment_is_source_backed(tmp_path: Path):
    source = tmp_path / "Target.sol"
    source.write_text(
        "contract Target { mapping(address => uint256) public queued; "
        "function step(address user, uint256 amount) external { "
        "queued[user] = queued[user] + amount; } }",
        encoding="utf-8",
    )
    from cydra.models import ParameterModel
    model = ContractModel(
        "Target", str(source),
        (
            FunctionModel(
                "step", "external", (), ("queued",), (), 1,
                parameters=(
                    ParameterModel("user", "address"),
                    ParameterModel("amount", "uint256"),
                ),
            ),
        ),
        state_variables=("queued",),
    )
    relations = plan_source_state_relations(model, model.functions[0])
    assert len(relations) == 1
    assert relations[0].index_expressions == ("user",)
    assert relations[0].rhs_expression == "amount"


def test_direct_assignment_with_dynamic_local_fails_closed(tmp_path: Path):
    source = tmp_path / "Target.sol"
    source.write_text(
        "contract Target { uint256 public counter; "
        "function step(uint256 amount) external { "
        "uint256 delta = amount + 1; counter = counter + delta; } }",
        encoding="utf-8",
    )
    from cydra.models import ParameterModel
    model = ContractModel(
        "Target", str(source),
        (
            FunctionModel(
                "step", "external", (), ("counter",), (), 1,
                parameters=(ParameterModel("amount", "uint256"),),
            ),
        ),
        state_variables=("counter",),
    )
    assert plan_source_state_relations(model, model.functions[0]) == ()
