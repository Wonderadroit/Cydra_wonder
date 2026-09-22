from pathlib import Path

from cydra.execution_readiness import inspect_execution_readiness
from cydra.models import ConstructorModel, ContractModel, FunctionModel, ParameterModel


def test_readiness_discovers_constructor_roles_and_dependencies():
    model = ContractModel(
        "Target",
        str(Path("/tmp/Target.sol")),
        (),
        constructor=ConstructorModel(
            (
                ParameterModel("owner_", "address"),
                ParameterModel("asset_", "IERC20"),
                ParameterModel("riskManager_", "address"),
            ),
            1,
        ),
    )
    readiness = inspect_execution_readiness(model)
    kinds = {(item.kind, item.subject) for item in readiness.constructor_requirements}
    assert ("constructor_role", "owner") in kinds
    assert ("constructor_role", "risk_manager") in kinds
    assert ("constructor_dependency", "IERC20") in kinds


def test_readiness_discovers_caller_and_runtime_prerequisites():
    function = FunctionModel(
        "settle",
        "external",
        ("onlyOwner",),
        ("value",),
        (("LIQUIDATOR", "liquidate"),),
        10,
        authorization_predicates=("msg.sender == guardian",),
    )
    model = ContractModel("Target", "/tmp/Target.sol", (function,))
    readiness = inspect_execution_readiness(model, function)
    assert ("caller_role", "onlyOwner") in {(x.kind, x.subject) for x in readiness.caller_requirements}
    assert ("caller_predicate", "msg.sender == guardian") in {
        (x.kind, x.subject) for x in readiness.caller_requirements
    }
    assert ("runtime_dependency", "LIQUIDATOR.liquidate") in {
        (x.kind, x.subject) for x in readiness.runtime_requirements
    }


def test_readiness_records_modeled_state_predicates():
    function = FunctionModel(
        "configure", "external", (), ("limit",), (), 20,
        state_predicates=("limit > 0",),
    )
    model = ContractModel("Target", "/tmp/Target.sol", (function,))
    readiness = inspect_execution_readiness(model, function)
    assert readiness.state_requirements[0].subject == "limit > 0"


def test_execution_readiness_identifies_constructible_state_setup_candidates():
    contract = ContractModel(
        name="Target",
        source="Target.sol",
        functions=(
            FunctionModel("target", "external", (), (), (), 1, state_predicates=("items > 0",)),
            FunctionModel("seed", "external", ("onlyOwner",), ("items",), (), 2,
                          parameters=(ParameterModel("item", "address"),)),
        ),
    )
    readiness = inspect_execution_readiness(contract, contract.functions[0])
    assert [item.subject for item in readiness.state_setup_candidates] == ["seed"]
    assert readiness.state_setup_candidates[0].status == "constructible"


def test_execution_readiness_preserves_revert_guard_polarity():
    contract = ContractModel(
        name="Target",
        source="Target.sol",
        functions=(
            FunctionModel(
                "target", "external", (), (), (), 1,
                state_predicates=("count > 0",),
                state_predicate_polarities=(("count > 0", "must_not_hold"),),
            ),
        ),
    )
    readiness = inspect_execution_readiness(contract, contract.functions[0])
    assert readiness.state_requirements[0].status == "required"
    assert "must not hold" in readiness.state_requirements[0].detail
    assert readiness.state_setup_candidates == ()
