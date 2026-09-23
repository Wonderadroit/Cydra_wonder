from cydra.ast_dataflow import SemanticRelationshipEvidence
from pathlib import Path

from cydra.compiler_constraints import ConstraintEvidence
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


def test_readiness_excludes_resolved_library_calls_from_runtime_blockers(tmp_path):
    lib = tmp_path / "SafeLib.sol"
    lib.write_text("library SafeLib { function foo(uint256 x) internal pure returns (uint256) { return x; } }", encoding="utf-8")
    source = tmp_path / "Target.sol"
    source.write_text('import "./SafeLib.sol"; contract Target {}', encoding="utf-8")
    function = FunctionModel("configure", "external", (), (), (("SafeLib", "foo"),), 1)
    readiness = inspect_execution_readiness(ContractModel("Target", str(source), (function,)), function)
    assert readiness.runtime_requirements == ()


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


def test_execution_readiness_derives_setup_from_unknown_positive_collection_guard():
    contract = ContractModel(
        name="Target",
        source="Target.sol",
        functions=(
            FunctionModel(
                "target", "external", (), (), (), 1,
                state_predicates=("items.length > 0",),
                state_predicate_polarities=(("items.length > 0", "unknown"),),
            ),
            FunctionModel(
                "seed", "external", (), ("items",), (), 2,
                parameters=(ParameterModel("item", "address"),),
            ),
        ),
    )
    readiness = inspect_execution_readiness(contract, contract.functions[0])
    assert any(item.subject == "seed" and item.status == "constructible" for item in readiness.state_setup_candidates)


def test_execution_readiness_derives_setup_from_nonempty_collection_guard():
    contract = ContractModel(
        name="Target",
        source="Target.sol",
        functions=(
            FunctionModel(
                "target", "external", (), (), (), 1,
                state_predicates=("items.length == 0",),
                state_predicate_polarities=(("items.length == 0", "must_not_hold"),),
            ),
            FunctionModel(
                "seed", "external", ("onlyOwner",), (), (("items", "push"),), 2,
                parameters=(ParameterModel("item", "address"),),
            ),
        ),
    )
    readiness = inspect_execution_readiness(contract, contract.functions[0])
    assert any(item.subject == "seed" and item.status == "constructible" for item in readiness.state_setup_candidates)


def test_execution_readiness_marks_external_setup_dependency_unresolved():
    contract = ContractModel(
        name="Target",
        source="Target.sol",
        functions=(
            FunctionModel("target", "external", (), (), (), 1, state_predicates=("items.length > 0",)),
            FunctionModel(
                "seed", "external", (), ("items",), (("tranche", "asset"),), 2,
                parameters=(ParameterModel("tranche", "address"),),
            ),
        ),
    )
    readiness = inspect_execution_readiness(contract, contract.functions[0])
    candidate = next(item for item in readiness.state_setup_candidates if item.subject == "seed")
    assert candidate.status == "unresolved"
    assert "runtime dependencies" in candidate.detail


def test_execution_readiness_uses_compiler_collection_constraints_for_setup_discovery():
    contract = ContractModel(
        name="Target",
        source="Target.sol",
        functions=(
            FunctionModel("target", "external", (), (), (), 1,
                          parameters=(ParameterModel("index", "uint256"),)),
            FunctionModel("seed", "external", ("onlyOwner",), ("items",), (), 2,
                          parameters=(ParameterModel("item", "address"),)),
        ),
    )
    constraint = ConstraintEvidence(
        contract="Target",
        function="target",
        parameter="index",
        parameter_index=0,
        predicate="index >= items.length",
        source="solc-json-ast:test",
        kind="revert_guard",
    )
    readiness = inspect_execution_readiness(contract, contract.functions[0], (constraint,))
    assert any(item.subject == "index >= items.length" for item in readiness.state_requirements)
    assert any(item.subject == "seed" for item in readiness.state_setup_candidates)



def test_execution_readiness_preserves_local_guard_as_path_prerequisite():
    function = FunctionModel(
        "start", "external", (), (), (), 1,
        execution_predicates=("startDebt == 0",),
        execution_predicate_polarities=(("startDebt == 0", "must_not_hold"),),
    )
    readiness = inspect_execution_readiness(ContractModel("Target", "Target.sol", (function,)), function)
    requirement = readiness.execution_requirements[0]
    assert requirement.kind == "execution_predicate"
    assert requirement.status == "required"
    assert "must not hold" in requirement.detail
    assert not readiness.state_setup_candidates



def test_execution_readiness_exposes_call_result_dataflow():
    function = FunctionModel(
        "target", "external", (), (), (), 1,
        execution_predicates=("startDebt == 0",),
        execution_predicate_polarities=(("startDebt == 0", "must_not_hold"),),
        execution_value_bindings=(("startDebt", "maxWithdraw(msg.sender)"),),
    )
    readiness = inspect_execution_readiness(ContractModel("Target", "Target.sol", (function,)), function)
    assert any(r.kind == "execution_dataflow" and "maxWithdraw(msg.sender)" in r.subject for r in readiness.execution_requirements)


def test_execution_readiness_resolves_local_call_result_producer():
    producer = FunctionModel(
        "maxWithdraw",
        "internal",
        (),
        (),
        (),
        1,
        return_expressions=("debt",),
    )
    consumer = FunctionModel(
        "start",
        "external",
        (),
        (),
        (),
        5,
        execution_predicates=("startDebt == 0",),
        execution_predicate_polarities=(("startDebt == 0", "must_not_hold"),),
        execution_value_bindings=(("startDebt", "maxWithdraw(msg.sender)"),),
    )
    contract = ContractModel("Target", "Target.sol", (producer, consumer))

    readiness = inspect_execution_readiness(contract, consumer)
    producer_requirements = [
        item for item in readiness.execution_requirements
        if item.kind == "execution_value_producer"
    ]

    assert len(producer_requirements) == 1
    assert producer_requirements[0].subject == "startDebt <- maxWithdraw(debt)"
    assert producer_requirements[0].status == "discovered"
    assert "satisfiability" in producer_requirements[0].detail


def test_execution_readiness_keeps_unknown_execution_producer_unresolved():
    consumer = FunctionModel(
        "start",
        "external",
        (),
        (),
        (),
        5,
        execution_predicates=("startDebt == 0",),
        execution_predicate_polarities=(("startDebt == 0", "must_not_hold"),),
        execution_value_bindings=(("startDebt", "maxWithdraw(msg.sender)"),),
    )
    contract = ContractModel("Target", "Target.sol", (consumer,))

    readiness = inspect_execution_readiness(contract, consumer)
    assert not any(item.kind == "execution_value_producer" for item in readiness.execution_requirements)
    dataflow = [item for item in readiness.execution_requirements if item.kind == "execution_dataflow"]
    assert len(dataflow) == 1
    assert dataflow[0].status == "required"


def test_execution_readiness_uses_inherited_producer_models():
    inherited = FunctionModel(
        "maxWithdraw",
        "public",
        (),
        (),
        (),
        1,
        return_expressions=("debt",),
    )
    consumer = FunctionModel(
        "start",
        "external",
        (),
        (),
        (),
        5,
        execution_predicates=("startDebt == 0",),
        execution_predicate_polarities=(("startDebt == 0", "must_not_hold"),),
        execution_value_bindings=(("startDebt", "maxWithdraw(msg.sender)"),),
    )
    contract = ContractModel("Derived", "Derived.sol", (consumer,), inherited_functions=(inherited,))

    readiness = inspect_execution_readiness(contract, consumer)
    assert any(
        item.kind == "execution_value_producer"
        and item.subject == "startDebt <- maxWithdraw(debt)"
        for item in readiness.execution_requirements
    )


def test_execution_readiness_uses_compiler_state_effects_for_setup_candidates():
    from cydra.ast_dataflow import SemanticRelationshipEvidence

    contract = ContractModel(
        name="Target",
        source="Target.sol",
        functions=(
            FunctionModel("target", "external", (), (), (), 1, state_predicates=("debt > 0",)),
            FunctionModel("borrow", "external", (), (), (), 2),
        ),
    )
    semantic = (
        SemanticRelationshipEvidence(
            contract="Target",
            function="borrow",
            relation="writes",
            target="debt",
            confidence=0.99,
            source="solc-json-ast:test",
        ),
    )

    readiness = inspect_execution_readiness(contract, contract.functions[0], semantic_evidence=semantic)
    assert any(item.subject == "borrow" for item in readiness.state_setup_candidates)


def test_execution_readiness_exposes_compiler_state_dependencies_of_value_producer():
    from cydra.ast_dataflow import SemanticRelationshipEvidence

    producer = FunctionModel(
        "maxWithdraw",
        "public",
        (),
        (),
        (),
        1,
        return_expressions=("convertToAssets(balanceOf[owner])",),
    )
    consumer = FunctionModel(
        "start",
        "external",
        (),
        (),
        (),
        5,
        execution_predicates=("startDebt == 0",),
        execution_predicate_polarities=(("startDebt == 0", "must_not_hold"),),
        execution_value_bindings=(("startDebt", "maxWithdraw(msg.sender)"),),
    )
    contract = ContractModel("Target", "Target.sol", (producer, consumer))
    semantic = (
        SemanticRelationshipEvidence(
            contract="Target",
            function="maxWithdraw",
            relation="reads",
            target="realisedDebt",
            confidence=0.99,
            source="solc-json-ast:test",
        ),
    )

    readiness = inspect_execution_readiness(contract, consumer, semantic_evidence=semantic)
    assert any(
        item.kind == "execution_state_dependency"
        and item.subject == "maxWithdraw -> realisedDebt"
        for item in readiness.execution_requirements
    )

def test_execution_value_producer_uses_contract_qualified_state_effects():
    contract = ContractModel(
        name="Target",
        source="Target.sol",
        functions=(
            FunctionModel(
                "consumer", "external", (), (), (), 1,
                execution_predicates=("startDebt == 0",),
                execution_predicate_polarities=(("startDebt == 0", "unknown"),),
                execution_value_bindings=(("startDebt", "producer()"),),
            ),
            FunctionModel(
                "producer", "internal", (), (), (), 2,
                return_expressions=("balanceOf[owner]",),
            ),
        ),
        inherited_functions=(),
    )
    evidence = (
        SemanticRelationshipEvidence(
            contract="Target",
            function="producer",
            relation="reads",
            target="balanceOf",
            confidence=0.98,
            source="solc-json-ast:Target.sol",
        ),
    )
    readiness = inspect_execution_readiness(contract, contract.functions[0], semantic_evidence=evidence)
    assert any(item.kind == "execution_state_dependency" and item.subject == "producer -> balanceOf" for item in readiness.execution_requirements)
