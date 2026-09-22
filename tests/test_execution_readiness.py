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
