from pathlib import Path

from cydra.models import ContractModel, FunctionModel
from cydra.runtime_observation import plan_public_state_observations


def test_public_scalar_state_predicate_gets_runtime_observation(tmp_path):
    source = tmp_path / "Target.sol"
    source.write_text(
        "contract Target { uint256 public epoch; function use() external { require(epoch > 0); } }",
        encoding="utf-8",
    )
    model = ContractModel(
        "Target",
        str(source),
        (
            FunctionModel(
                "use", "external", (), (), (), 1,
                state_predicates=("epoch > 0",),
                state_predicate_polarities=(("epoch > 0", "must_hold"),),
            ),
        ),
    )
    plans = plan_public_state_observations(model, model.functions[0])
    assert len(plans) == 1
    assert plans[0].getter == "target.epoch()"
    assert plans[0].expression == "target.epoch() > 0"


def test_reverting_guard_observation_checks_the_negation(tmp_path):
    source = tmp_path / "Target.sol"
    source.write_text(
        "contract Target { uint256 public epoch; function use() external { if (epoch == 0) revert(); } }",
        encoding="utf-8",
    )
    model = ContractModel(
        "Target",
        str(source),
        (
            FunctionModel(
                "use", "external", (), (), (), 1,
                state_predicates=("epoch == 0",),
                state_predicate_polarities=(("epoch == 0", "must_not_hold"),),
            ),
        ),
    )
    plans = plan_public_state_observations(model, model.functions[0])
    assert plans[0].expression == "!(target.epoch() == 0)"


def test_non_public_or_complex_state_is_fail_closed(tmp_path):
    source = tmp_path / "Target.sol"
    source.write_text(
        "contract Target { uint256 private epoch; mapping(address => uint256) public balance; }",
        encoding="utf-8",
    )
    model = ContractModel(
        "Target",
        str(source),
        (
            FunctionModel(
                "use", "external", (), (), (), 1,
                state_predicates=("epoch > 0", "balance > 0"),
                state_predicate_polarities=(
                    ("epoch > 0", "must_hold"),
                    ("balance > 0", "must_hold"),
                ),
            ),
        ),
    )
    assert plan_public_state_observations(model, model.functions[0]) == ()


def test_public_mapping_state_predicate_finds_inherited_source(tmp_path):
    base = tmp_path / "Base.sol"
    base.write_text(
        "contract Base { mapping(uint256 => address) public externalActionMap; }",
        encoding="utf-8",
    )
    source = tmp_path / "Target.sol"
    source.write_text(
        'import "./Base.sol"; contract Target is Base {}',
        encoding="utf-8",
    )
    model = ContractModel(
        "Target",
        str(source),
        (
            FunctionModel(
                "use", "external", (), (), (), 1,
                execution_predicates=(
                    "externalActionMap[id] == expected && "
                    "externalActionMap[id] != address(0)",
                ),
            ),
        ),
    )
    plans = plan_public_state_observations(model, model.functions[0])
    assert len(plans) == 1
    assert plans[0].getter == "target.externalActionMap(id)"


def test_public_mapping_state_observation_accepts_override_modifier(tmp_path):
    base = tmp_path / "Base.sol"
    base.write_text(
        "interface I { function externalActionMap(uint256) external view returns (address); } "
        "contract Base is I { mapping(uint256 => address) public override externalActionMap; }",
        encoding="utf-8",
    )
    source = tmp_path / "Target.sol"
    source.write_text(
        'import "./Base.sol"; contract Target is Base {}',
        encoding="utf-8",
    )
    model = ContractModel(
        "Target",
        str(source),
        (
            FunctionModel(
                "use", "external", (), (), (), 1,
                execution_predicates=("externalActionMap[id] == expected",),
            ),
        ),
    )
    plans = plan_public_state_observations(model, model.functions[0])
    assert len(plans) == 1
    assert plans[0].getter == "target.externalActionMap(id)"


def test_public_mapping_observation_accepts_separate_nonzero_guard(tmp_path):
    base = tmp_path / "Base.sol"
    base.write_text(
        "contract Base { mapping(uint256 => address) public externalActionMap; }",
        encoding="utf-8",
    )
    source = tmp_path / "Target.sol"
    source.write_text(
        'import "./Base.sol"; contract Target is Base {}',
        encoding="utf-8",
    )
    model = ContractModel(
        "Target",
        str(source),
        (
            FunctionModel(
                "use", "external", (), (), (), 1,
                execution_predicates=(
                    "externalActionMap[id] == externalAddress && externalAddress != address(0)",
                ),
            ),
        ),
    )
    plans = plan_public_state_observations(model, model.functions[0])
    assert len(plans) == 1
    assert plans[0].getter == "target.externalActionMap(id)"


def test_public_mapping_state_predicate_finds_source_backed_observation(tmp_path):
    source = tmp_path / "Target.sol"
    source.write_text(
        "contract Target { mapping(bytes32 => bool) public usedMessages; }",
        encoding="utf-8",
    )
    model = ContractModel(
        "Target",
        str(source),
        (
            FunctionModel(
                "use", "external", (), (), (), 1,
                state_predicates=("usedMessages[key] == false",),
                state_predicate_polarities=(("usedMessages[key] == false", "must_hold"),),
            ),
        ),
    )
    plans = plan_public_state_observations(model, model.functions[0])
    assert len(plans) == 1
    assert plans[0].getter == "target.usedMessages(key)"
    assert plans[0].expression == "target.usedMessages(key) == false"
