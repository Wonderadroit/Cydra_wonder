from pathlib import Path

from cydra.models import ContractModel, FunctionModel
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
