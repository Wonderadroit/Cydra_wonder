from pathlib import Path

from cydra.models import ContractModel, FunctionModel, ParameterModel
from cydra.state_relation_observation import plan_state_relation_observations


def test_relation_observation_binds_public_scalar_getter(tmp_path: Path):
    source = tmp_path / "Target.sol"
    source.write_text(
        "contract Target { uint256 public counter; "
        "function bump() external { counter += 1; } }",
        encoding="utf-8",
    )
    model = ContractModel(
        "Target",
        str(source),
        (FunctionModel("bump", "external", (), ("counter",), (), 2),),
        state_variables=("counter",),
    )
    plans = plan_state_relation_observations(model, model.functions[0])
    assert len(plans) == 1
    assert plans[0].getter == "target.counter()"
    assert plans[0].relation.expression == "after(counter) == before(counter) + 1"


def test_relation_observation_fails_closed_without_public_getter(tmp_path: Path):
    source = tmp_path / "Target.sol"
    source.write_text(
        "contract Target { uint256 private counter; "
        "function bump() external { counter += 1; } }",
        encoding="utf-8",
    )
    model = ContractModel(
        "Target",
        str(source),
        (FunctionModel("bump", "external", (), ("counter",), (), 2),),
        state_variables=("counter",),
    )
    assert plan_state_relation_observations(model, model.functions[0]) == ()


def test_relation_observation_fails_closed_for_signed_scalar(tmp_path: Path):
    source = tmp_path / "Target.sol"
    source.write_text(
        "contract Target { int256 public counter; "
        "function bump() external { counter += 1; } }",
        encoding="utf-8",
    )
    model = ContractModel(
        "Target",
        str(source),
        (FunctionModel("bump", "external", (), ("counter",), (), 2),),
        state_variables=("counter",),
    )
    assert plan_state_relation_observations(model, model.functions[0]) == ()


def test_relation_observation_binds_nested_public_mapping_getter(tmp_path: Path):
    source = tmp_path / "Target.sol"
    source.write_text(
        "contract Target { "
        "mapping(address => mapping(uint256 => uint256)) public queued; "
        "function execute(address user, uint256 epoch) external { queued[user][epoch] += 1; } }",
        encoding="utf-8",
    )
    model = ContractModel(
        "Target",
        str(source),
        (
            FunctionModel(
                "execute",
                "external",
                (),
                ("queued",),
                (),
                2,
                parameters=(
                    ParameterModel("user", "address"),
                    __import__("cydra.models", fromlist=["ParameterModel"]).ParameterModel("epoch", "uint256"),
                ),
            ),
        ),
        state_variables=("queued",),
    )
    plans = plan_state_relation_observations(model, model.functions[0])
    assert len(plans) == 1
    assert plans[0].getter == "target.queued(user, epoch)"
    assert plans[0].state_type == "uint256"
    assert plans[0].relation.index_expressions == ("user", "epoch")


def test_relation_observation_fails_closed_for_dynamic_mapping_index(tmp_path: Path):
    source = tmp_path / "Target.sol"
    source.write_text(
        "contract Target { mapping(address => uint256) public queued; "
        "function execute(address user) external { "
        "address key = msg.sender; queued[key] += 1; } }",
        encoding="utf-8",
    )
    model = ContractModel(
        "Target",
        str(source),
        (
            FunctionModel(
                "execute", "external", (), ("queued",), (), 2,
                parameters=(
                    __import__("cydra.models", fromlist=["ParameterModel"]).ParameterModel("user", "address"),
                ),
            ),
        ),
        state_variables=("queued",),
    )
    assert plan_state_relation_observations(model, model.functions[0]) == ()


def test_relation_observation_binds_parameter_delta(tmp_path: Path):
    source = tmp_path / "Target.sol"
    source.write_text(
        "contract Target { uint256 public counter; "
        "function bump(uint256 amount) external { counter += amount; } }",
        encoding="utf-8",
    )
    model = ContractModel(
        "Target",
        str(source),
        (
            FunctionModel(
                "bump", "external", (), ("counter",), (), 2,
                parameters=(ParameterModel("amount", "uint256"),),
            ),
        ),
        state_variables=("counter",),
    )
    plans = plan_state_relation_observations(model, model.functions[0])
    assert len(plans) == 1
    assert plans[0].relation.rhs_expression == "amount"


def test_relation_observation_rejects_non_numeric_parameter_delta(tmp_path: Path):
    source = tmp_path / "Target.sol"
    source.write_text(
        "contract Target { uint256 public counter; "
        "function bump(bool enabled) external { counter += enabled; } }",
        encoding="utf-8",
    )
    model = ContractModel(
        "Target",
        str(source),
        (
            FunctionModel(
                "bump", "external", (), ("counter",), (), 2,
                parameters=(ParameterModel("enabled", "bool"),),
            ),
        ),
        state_variables=("counter",),
    )
    assert plan_state_relation_observations(model, model.functions[0]) == ()


def test_relation_observation_binds_caller_and_state_indexes(tmp_path: Path):
    source = tmp_path / "Target.sol"
    source.write_text(
        "contract Target { "
        "uint128 public depositEpoch; "
        "mapping(address => mapping(uint256 => uint128)) public queuedDeposit; "
        "function requestDeposit(uint128 assets) external { "
        "queuedDeposit[msg.sender][depositEpoch] += assets; } }",
        encoding="utf-8",
    )
    model = ContractModel(
        "Target",
        str(source),
        (
            FunctionModel(
                "requestDeposit", "external", (), ("queuedDeposit",), (), 4,
                parameters=(ParameterModel("assets", "uint128"),),
            ),
        ),
        state_variables=("depositEpoch", "queuedDeposit"),
    )
    plans = plan_state_relation_observations(model, model.functions[0])
    assert len(plans) == 1
    assert plans[0].getter == "target.queuedDeposit(msg.sender, target.depositEpoch())"

    
def test_relation_observation_records_state_backed_index_type(tmp_path: Path):
    source = tmp_path / "Target.sol"
    source.write_text(
        "contract Target { "
        "uint128 public epoch; "
        "mapping(uint256 => uint256) public queued; "
        "function queue(uint256 amount) external { queued[epoch] += amount; } }",
        encoding="utf-8",
    )
    model = ContractModel(
        "Target",
        str(source),
        (
            FunctionModel(
                "queue", "external", (), ("queued",), (), 4,
                parameters=(ParameterModel("amount", "uint256"),),
            ),
        ),
        state_variables=("epoch", "queued"),
    )
    plans = plan_state_relation_observations(model, model.functions[0])
    assert len(plans) == 1
    assert plans[0].index_state_types == (("epoch", "uint128"),)


def test_relation_observation_falls_back_to_compiler_storage_for_private_mapping(tmp_path, monkeypatch):
    from cydra import state_relation_observation as module

    source = tmp_path / "Target.sol"
    source.write_text(
        "contract Target { "
        "mapping(address => mapping(uint256 => uint128)) private queued; "
        "function execute(uint256 epoch, uint128 amount) external { "
        "queued[msg.sender][epoch] += amount; } }",
        encoding="utf-8",
    )
    model = ContractModel(
        "Target",
        str(source),
        (
            FunctionModel(
                "execute", "external", (), ("queued",), (), 2,
                parameters=(
                    ParameterModel("epoch", "uint256"),
                    ParameterModel("amount", "uint128"),
                ),
            ),
        ),
        state_variables=("queued",),
    )
    monkeypatch.setattr(
        module,
        "_forge_storage_layout",
        lambda project, contract: {
            "storage": [{"label": "queued", "slot": "3", "offset": 0, "type": "t_mapping"}],
            "types": {
                "t_mapping": {"encoding": "mapping", "key": "t_address", "value": "t_mapping2"},
                "t_address": {"label": "address"},
                "t_mapping2": {"encoding": "mapping", "key": "t_uint256", "value": "t_uint128"},
                "t_uint256": {"label": "uint256"},
                "t_uint128": {"label": "uint128", "encoding": "inplace", "numberOfBytes": 16},
            },
        },
    )
    plans = plan_state_relation_observations(model, model.functions[0], tmp_path)
    assert len(plans) == 1
    assert plans[0].observation_kind == "compiler_storage"
    assert "vm.load(address(target)" in plans[0].getter
