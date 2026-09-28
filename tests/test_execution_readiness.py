from dataclasses import replace
from pathlib import Path

from cydra.compiler_constraints import ConstraintEvidence
from cydra.execution_readiness import inspect_execution_readiness, constructible_state_setup_plan, _caller_requirements
from cydra.models import ConstructorModel, ContractModel, FunctionModel, ModifierModel, ParameterModel
from cydra.solidity_model import parse_solidity


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

def test_lifecycle_modifiers_are_not_caller_role_prerequisites():
    function = FunctionModel("initialize", "external", ("initializer",), (), (), 1)
    model = ContractModel("Target", "/tmp/Target.sol", (function,))
    readiness = inspect_execution_readiness(model, function)
    assert readiness.caller_requirements == ()


def test_pure_input_execution_predicate_is_experiment_constraint():
    from cydra.execution_readiness import inspect_execution_readiness
    from cydra.models import ContractModel, FunctionModel, ParameterModel

    function = FunctionModel(
        name="initialize",
        visibility="public",
        modifiers=(),
        writes=(),
        external_calls=(),
        line=1,
        parameters=(ParameterModel("amount", "uint256"),),
        execution_predicates=("amount > 0",),
        execution_predicate_polarities=(("amount > 0", "must_hold"),),
    )
    contract = ContractModel(
        name="Target",
        source="/tmp/Target.sol",
        functions=(function,),
        state_variables=("storedAmount",),
    )
    readiness = inspect_execution_readiness(contract, function)
    assert readiness.execution_requirements[0].status == "constraint"


def test_call_derived_local_execution_predicate_remains_blocking():
    from cydra.execution_readiness import inspect_execution_readiness
    from cydra.models import ContractModel, FunctionModel

    function = FunctionModel(
        name="execute",
        visibility="external",
        modifiers=(),
        writes=(),
        external_calls=(),
        line=1,
        execution_predicates=("startDebt == 0",),
        execution_predicate_polarities=(("startDebt == 0", "must_not_hold"),),
        execution_value_bindings=(("startDebt", "maxWithdraw(msg.sender)"),),
    )
    contract = ContractModel(
        name="Target",
        source="/tmp/Target.sol",
        functions=(function,),
    )
    readiness = inspect_execution_readiness(contract, function)
    assert readiness.execution_requirements[0].status == "required"


def test_state_execution_predicate_remains_blocking():
    from cydra.execution_readiness import inspect_execution_readiness
    from cydra.models import ContractModel, FunctionModel

    function = FunctionModel(
        name="execute",
        visibility="external",
        modifiers=(),
        writes=(),
        external_calls=(),
        line=1,
        execution_predicates=("storedAmount > 0",),
        execution_predicate_polarities=(("storedAmount > 0", "must_hold"),),
    )
    contract = ContractModel(
        name="Target",
        source="/tmp/Target.sol",
        functions=(function,),
        state_variables=("storedAmount",),
    )
    readiness = inspect_execution_readiness(contract, function)
    assert readiness.execution_requirements[0].status == "required"


def test_repeated_unbound_local_scalar_can_be_an_experiment_constraint():
    from cydra.execution_readiness import inspect_execution_readiness
    from cydra.models import ContractModel, FunctionModel

    function = FunctionModel(
        name="initialize",
        visibility="public",
        modifiers=(),
        writes=(),
        external_calls=(),
        line=1,
        execution_predicates=("decimals < 18", "decimals != 18"),
        execution_predicate_polarities=(
            ("decimals < 18", "must_not_hold"),
            ("decimals != 18", "must_not_hold"),
        ),
    )
    contract = ContractModel(
        name="Target",
        source="/tmp/Target.sol",
        functions=(function,),
    )
    readiness = inspect_execution_readiness(contract, function)
    assert all(item.status == "constraint" for item in readiness.execution_requirements)


def test_constructible_constructor_interface_and_role_inputs_are_constraints():
    model = ContractModel(
        "Target",
        "/tmp/Target.sol",
        (),
        constructor=ConstructorModel(
            (
                ParameterModel("factory_", "address"),
                ParameterModel("accountant_", "IVaultAccountant"),
            ),
            1,
            interface_casts=(("accountant_", "IVaultAccountant"),),
        ),
    )
    readiness = inspect_execution_readiness(model)
    statuses = {(item.kind, item.subject): item.status for item in readiness.constructor_requirements}
    assert statuses[("constructor_role", "factory")] == "constraint"
    assert statuses[("constructor_dependency", "IVaultAccountant")] == "constraint"

def test_input_state_order_guard_is_experiment_constraint() -> None:
    model = ContractModel(
        "Target",
        "/tmp/Target.sol",
        functions=(
            FunctionModel(
                "execute",
                "external",
                (),
                (),
                (),
                1,
                parameters=(ParameterModel("epoch", "uint256"),),
                execution_predicates=("epoch >= depositEpoch",),
                execution_predicate_polarities=(("epoch >= depositEpoch", "must_not_hold"),),
            ),
        ),
        state_variables=("depositEpoch",),
    )
    readiness = inspect_execution_readiness(model, model.functions[0])
    predicates = {
        (item.kind, item.subject): item.status
        for item in readiness.execution_requirements
    }
    assert predicates[("execution_predicate", "epoch >= depositEpoch")] == "constraint"


def test_execution_readiness_treats_solidity_casts_as_deterministic_dataflow():
    function = FunctionModel(
        "runAction",
        "external",
        (),
        (),
        (),
        1,
        execution_predicates=("selector == expected", "balanceChange < 0"),
        execution_predicate_polarities=(
            ("selector == expected", "must_not_hold"),
            ("balanceChange < 0", "must_not_hold"),
        ),
        execution_value_bindings=(
            ("selector", "bytes4(op.callData)"),
            ("balanceChange", "int256(after[i]) - int256(before[i])"),
        ),
    )
    readiness = inspect_execution_readiness(ContractModel("Target", "Target.sol", (function,)), function)
    dataflow = {
        item.subject: item.status
        for item in readiness.execution_requirements
        if item.kind == "execution_dataflow"
    }
    assert dataflow["selector <- bytes4(op.callData)"] == "constraint"
    assert dataflow["balanceChange <- int256(after[i]) - int256(before[i])"] == "constraint"


def test_execution_readiness_excludes_solidity_abi_builtin_runtime_dependency():
    function = FunctionModel(
        "runAction",
        "external",
        (),
        (),
        (("abi", "decode"), ("target", "execute")),
        1,
    )
    readiness = inspect_execution_readiness(ContractModel("Target", "Target.sol", (function,)), function)
    assert ("runtime_dependency", "abi.decode") not in {
        (item.kind, item.subject) for item in readiness.runtime_requirements
    }
    assert ("runtime_dependency", "target.execute") in {
        (item.kind, item.subject) for item in readiness.runtime_requirements
    }


def test_execution_readiness_does_not_reclassify_deterministic_casts_as_producer_dependencies():
    function = FunctionModel(
        "runAction",
        "external",
        (),
        (),
        (),
        1,
        execution_predicates=("selector == expected", "balanceChange < 0"),
        execution_predicate_polarities=(
            ("selector == expected", "must_not_hold"),
            ("balanceChange < 0", "must_not_hold"),
        ),
        execution_value_bindings=(
            ("selector", "bytes4(op.callData)"),
            ("balanceChange", "int256(after[i]) - int256(before[i])"),
        ),
    )
    readiness = inspect_execution_readiness(ContractModel("Target", "Target.sol", (function,)), function)
    assert not any(
        item.kind in {"execution_value_dependency", "execution_value_runtime_dependency"}
        for item in readiness.execution_requirements
    )


def test_execution_readiness_does_not_treat_returned_local_collection_as_runtime_target():
    function = FunctionModel(
        "runAction",
        "external",
        (),
        (),
        (("utxoSet", "skipLast"),),
        1,
        return_expressions=("utxoSet",),
    )
    model = ContractModel("Target", "Target.sol", (function,))
    readiness = inspect_execution_readiness(model, function)
    assert not any(
        item.subject == "utxoSet.skipLast"
        for item in readiness.runtime_requirements
    )

    
def test_execution_readiness_allows_deterministic_local_guard_with_cast_binding():
    function = FunctionModel(
        "runAction",
        "external",
        (),
        (),
        (),
        1,
        execution_predicates=("balanceChange < 0",),
        execution_predicate_polarities=(("balanceChange < 0", "must_not_hold"),),
        execution_value_bindings=(
            ("balanceChange", "int256(after[i]) - int256(before[i])"),
        ),
    )
    readiness = inspect_execution_readiness(ContractModel("Target", "Target.sol", (function,)), function)
    assert readiness.execution_requirements[0].status == "constraint"


def test_callback_reachability_capability_allows_external_call_outcome_guard():
    function = FunctionModel(
        "runAction",
        "external",
        (),
        (),
        (("op", "call"),),
        1,
        execution_predicates=("!success",),
        execution_predicate_polarities=(("!success", "must_not_hold"),),
        execution_value_bindings=(
            ("success", "op.endpoint.call(op.callData)"),
        ),
    )
    contract = ContractModel("Target", "Target.sol", (function,))
    blocked = inspect_execution_readiness(contract, function)
    assert blocked.execution_requirements[0].status == "required"
    reachable = inspect_execution_readiness(
        contract,
        function,
        execution_capabilities=frozenset({"callback_state_order_reachability"}),
    )
    assert reachable.execution_requirements[0].status == "constraint"


def test_callback_reachability_capability_allows_selected_external_member_call_outcome():
    function = FunctionModel(
        "runAction",
        "external",
        (),
        (),
        (),
        1,
        execution_predicates=("!success",),
        execution_predicate_polarities=(("!success", "must_not_hold"),),
        execution_value_bindings=(
            ("success", "IHinkalWallet(stack.signerAddress).callHinkalWallet(op.endpoint, op.callData, op.value)"),
        ),
    )
    contract = ContractModel("Target", "Target.sol", (function,))
    blocked = inspect_execution_readiness(contract, function)
    assert blocked.execution_requirements[0].status == "required"
    reachable = inspect_execution_readiness(
        contract,
        function,
        execution_capabilities=frozenset({"callback_state_order_reachability"}),
    )
    assert reachable.execution_requirements[0].status == "constraint"


def test_internal_callee_execution_guards_propagate_into_caller_readiness(tmp_path):
    from cydra.execution_readiness import inspect_execution_readiness
    from cydra.models import ContractModel, FunctionModel

    source = tmp_path / "Target.sol"
    source.write_text(
        "contract Target {\\n"
        "    function runAction() external { verifyWallet(); }\\n"
        "    function verifyWallet() internal { if (!verified) revert(); }\\n"
        "}\\n",
        encoding="utf-8",
    )
    caller = FunctionModel(
        "runAction", "external", (), (), (), 2,
    )
    callee = FunctionModel(
        "verifyWallet", "internal", (), (), (), 3,
        execution_predicates=("!verified",),
        execution_predicate_polarities=(("!verified", "must_not_hold"),),
    )
    readiness = inspect_execution_readiness(
        ContractModel("Target", str(source), (caller, callee)), caller,
    )
    propagated = [
        item for item in readiness.execution_requirements
        if item.kind == "internal_execution_predicate"
    ]
    assert len(propagated) == 1
    assert propagated[0].subject == "verifyWallet: !verified"
    assert propagated[0].status == "unresolved"
    assert propagated[0].source == "runAction:internal-call->verifyWallet"


def test_internal_execution_prerequisite_categories_are_descriptive(tmp_path):
    source = tmp_path / "Target.sol"
    source.write_text("""
    contract Target {
        bool verified;
        function runAction(uint256 amount) external { verifyWallet(amount); }
        function verifyWallet(uint256 amount) internal {
            require(!verified);
            require(amount > 0);
        }
    }
    """)
    from cydra.solidity_model import parse_solidity
    contract = next(item for item in parse_solidity(source) if item.name == "Target")
    function = next(item for item in contract.functions if item.name == "runAction")
    readiness = inspect_execution_readiness(contract, function)
    categories = {item.category for item in readiness.execution_requirements if item.kind == "internal_execution_predicate"}
    assert "state_observation" in categories
    assert "input_construction" in categories
    assert all(item.status == "unresolved" for item in readiness.execution_requirements if item.kind == "internal_execution_predicate")


def test_internal_execution_temporal_prerequisite_is_execution_context(tmp_path):
    source = tmp_path / "Target.sol"
    source.write_text("""
    contract Target {
        function runAction() external { verify(); }
        function verify() internal {
            require(block.timestamp > deadline);
        }
    }
    """, encoding="utf-8")
    from cydra.solidity_model import parse_solidity
    contract = next(item for item in parse_solidity(source) if item.name == "Target")
    function = next(item for item in contract.functions if item.name == "runAction")
    readiness = inspect_execution_readiness(contract, function)
    propagated = next(
        item for item in readiness.execution_requirements
        if item.kind == "internal_execution_predicate"
    )
    assert propagated.category == "execution_context"
    assert propagated.status == "unresolved"


def test_internal_execution_local_crypto_witness_is_not_plain_input(tmp_path):
    source = tmp_path / "Target.sol"
    source.write_text("""
    contract Target {
        function runAction() external { verify(); }
        function verify() internal {
            (address recoveredAddress, uint8 err) = ECDSA.tryRecover(digest, v, r, s);
            bool verified = err == ECDSA.RecoverError.NoError &&
                recoveredAddress == signerAddress;
            require(!verified);
        }
    }
    """, encoding="utf-8")
    from cydra.solidity_model import parse_solidity
    contract = next(item for item in parse_solidity(source) if item.name == "Target")
    function = next(item for item in contract.functions if item.name == "runAction")
    readiness = inspect_execution_readiness(contract, function)
    propagated = next(
        item for item in readiness.execution_requirements
        if item.kind == "internal_execution_predicate"
    )
    assert propagated.category == "cryptographic_witness"
    assert propagated.status == "unresolved"

def test_internal_execution_input_prerequisite_can_be_an_experiment_constraint(tmp_path):
    source = tmp_path / "Target.sol"
    source.write_text("""
    contract Target {
        function runAction() external { verify(1); }
        function verify(uint256 amount) internal {
            require(amount > 0);
        }
    }
    """, encoding="utf-8")
    from cydra.solidity_model import parse_solidity
    contract = next(item for item in parse_solidity(source) if item.name == "Target")
    function = next(item for item in contract.functions if item.name == "runAction")
    readiness = inspect_execution_readiness(contract, function)
    propagated = next(
        item for item in readiness.execution_requirements
        if item.kind == "internal_execution_predicate"
    )
    assert propagated.subject == "verify: amount > 0"
    assert propagated.status == "constraint"
    assert propagated.category == "input_construction"

def test_internal_mapping_predicate_feeds_generic_state_setup_candidates(tmp_path):
    source = tmp_path / "Target.sol"
    source.write_text("""
    contract Target {
        mapping(uint256 => address) registry;
        function run(uint256 key) external { verify(key); }
        function verify(uint256 key) internal {
            require(registry[key] != address(0));
        }
        function register(uint256 key, address value) external {
            registry[key] = value;
        }
    }
    """, encoding="utf-8")
    from cydra.solidity_model import parse_solidity
    contract = next(item for item in parse_solidity(source) if item.name == "Target")
    function = next(item for item in contract.functions if item.name == "run")
    readiness = inspect_execution_readiness(contract, function)
    candidates = [
        item for item in readiness.state_setup_candidates
        if item.kind == "internal_state_setup_candidate"
    ]
    assert any(item.subject == "register" and item.status == "constructible" for item in candidates)


def test_internal_namespaced_state_observation_can_satisfy_erc7201_guard(tmp_path):
    storage = tmp_path / "EmporiumStorage.sol"
    storage.write_text(
        """
        contract EmporiumStorage {
            /// @custom:storage-location erc7201:test.storage
            struct Storage {
                address helper;
                mapping(uint256 => bool) usedMessages;
            }
            bytes32 private constant TestLocation =
                0x1000000000000000000000000000000000000000000000000000000000000000;
        }
        """,
        encoding="utf-8",
    )
    source = tmp_path / "Target.sol"
    (tmp_path / "foundry.toml").write_text("[profile.default]\n", encoding="utf-8")
    source.write_text(
        """
        import "./EmporiumStorage.sol";
        contract Target is EmporiumStorage {
            function run(uint256 message) external { verify(message); }
            function verify(uint256 message) internal {
                if ($.usedMessages[message]) revert();
            }
        }
        """,
        encoding="utf-8",
    )
    caller = FunctionModel("run", "external", (), (), (), 5)
    callee = FunctionModel(
        "verify", "internal", (), (), (), 6,
        execution_predicates=("$.usedMessages[message]",),
        execution_predicate_polarities=(("$.usedMessages[message]", "must_not_hold"),),
    )
    readiness = inspect_execution_readiness(
        ContractModel(
            "Target",
            str(source),
            (caller, callee),
            inherits=("EmporiumStorage",),
        ),
        caller,
    )
    propagated = next(
        item for item in readiness.execution_requirements
        if item.kind == "internal_execution_predicate"
    )
    assert propagated.category == "state_observation"
    assert propagated.status == "constraint"


def test_nonreentrant_modifier_is_not_a_caller_role():
    from cydra.models import FunctionModel, Parameter
    from cydra.execution_readiness import _caller_requirements

    function = FunctionModel(
        name="transact",
        visibility="external",
        modifiers=("nonReentrant",),
        writes=(),
        external_calls=(),
        line=1,
    )
    assert _caller_requirements(function) == ()


def test_namespaced_interface_struct_constructor_dependency_is_constructible(tmp_path):
    interface = tmp_path / "IMerkle.sol"
    interface.write_text(
        "interface IMerkle { struct MerkleConstructorArgs { uint128 levels; address poseidon2; } }\n",
        encoding="utf-8",
    )
    source = tmp_path / "Target.sol"
    source.write_text(
        'pragma solidity ^0.8.20; import "./IMerkle.sol"; '
        'contract Target { constructor(IMerkle.MerkleConstructorArgs memory args) {} }\n',
        encoding="utf-8",
    )
    model = ContractModel(
        "Target",
        str(source),
        (),
        constructor=ConstructorModel(
            (ParameterModel("args", "IMerkle.MerkleConstructorArgs"),),
            1,
        ),
    )
    readiness = inspect_execution_readiness(model)
    dependency = next(
        item for item in readiness.constructor_requirements
        if item.kind == "constructor_dependency"
    )
    assert dependency.subject == "IMerkle.MerkleConstructorArgs"
    assert dependency.status == "constraint"



def test_execution_readiness_treats_parameter_equal_caller_as_constructible_input():
    function = FunctionModel(
        "transact", "external", (), (), (), 1,
        parameters=(ParameterModel("data", "Data"),),
        execution_predicates=("data.externalAddress == msg.sender",),
        execution_predicate_polarities=(("data.externalAddress == msg.sender", "must_hold"),),
    )
    contract = ContractModel("Target", "Target.sol", (function,))
    readiness = inspect_execution_readiness(contract, function)
    requirement = readiness.execution_requirements[0]
    assert requirement.status == "constraint"
    assert requirement.category == "input_construction"


def test_execution_readiness_treats_msg_value_equal_parameter_as_constructible_input():
    predicate = "msg.value == _value"
    function = FunctionModel(
        "transfer", "internal", (), (), (), 1,
        parameters=(ParameterModel("_value", "uint256"),),
        execution_predicates=(predicate,),
        execution_predicate_polarities=((predicate, "must_hold"),),
    )
    contract = ContractModel("Target", "Target.sol", (function,))
    readiness = inspect_execution_readiness(contract, function)
    requirement = readiness.execution_requirements[0]
    assert requirement.status == "constraint"
    assert requirement.category == "unknown"


def test_runtime_dependency_constructor_interface_binding_is_constructible(tmp_path):
    helper = tmp_path / "IHelper.sol"
    helper.write_text(
        """
        interface IHelper {
            function performChecks() external view returns (uint256[] memory);
        }
        """,
        encoding="utf-8",
    )
    source = tmp_path / "Target.sol"
    source.write_text(
        """
        pragma solidity ^0.8.20;
        import "./IHelper.sol";
        contract Target {
            IHelper internal helper;
            constructor(address helper_) {
                helper = IHelper(helper_);
            }
            function run() external {
                helper.performChecks();
            }
        }
        """,
        encoding="utf-8",
    )
    from cydra.solidity_model import parse_solidity
    contract = next(item for item in parse_solidity(source) if item.name == "Target")
    function = next(item for item in contract.functions if item.name == "run")
    readiness = inspect_execution_readiness(contract, function)
    requirement = next(item for item in readiness.runtime_requirements)
    assert requirement.status == "constructible"
    assert "generic runtime-stub capability" in requirement.detail


def test_state_setup_planner_can_use_internal_state_writer_without_hardcoding(tmp_path):
    source = tmp_path / "Target.sol"
    source.write_text(
        """
        pragma solidity ^0.8.20;
        contract Target {
            mapping(uint256 => address) registry;
            function run(Data calldata data) external { verify(data); }
            function verify(Data calldata data) internal {
                require(registry[data.key] == data.endpoint);
            }
            function register(uint256 key, address endpoint) external {
                registry[key] = endpoint;
            }
            struct Data { uint256 key; address endpoint; }
        }
        """,
        encoding="utf-8",
    )
    from cydra.solidity_model import parse_solidity
    contract = next(item for item in parse_solidity(source) if item.name == "Target")
    function = next(item for item in contract.functions if item.name == "run")
    plan = constructible_state_setup_plan(contract, function)
    assert tuple(action.function for action in plan) == ("register",)


def test_state_setup_candidate_fails_closed_on_unresolved_custom_modifier(tmp_path):
    source = tmp_path / "Target.sol"
    source.write_text(
        """
        pragma solidity ^0.8.20;
        contract Target {
            mapping(uint256 => address) registry;
            function run(uint256 key) external { verify(key); }
            function verify(uint256 key) internal {
                require(registry[key] != address(0));
            }
            function register(uint256 key, address endpoint) external onlyRole(DEFAULT_ADMIN_ROLE) {
                registry[key] = endpoint;
            }
        }
        """,
        encoding="utf-8",
    )
    from cydra.solidity_model import parse_solidity
    contract = next(item for item in parse_solidity(source) if item.name == "Target")
    function = next(item for item in contract.functions if item.name == "run")
    readiness = inspect_execution_readiness(contract, function)
    candidate = next(
        item for item in readiness.state_setup_candidates
        if item.subject == "register"
    )
    assert candidate.status == "unresolved"
    assert "authorization" in candidate.detail



def test_state_setup_candidate_uses_resolved_inherited_modifier_authorization(tmp_path):
    source = tmp_path / "Target.sol"
    source.write_text(
        """
        pragma solidity ^0.8.20;
        contract Target {
            mapping(uint256 => address) registry;
            function run(uint256 key) external { verify(key); }
            function verify(uint256 key) internal {
                require(registry[key] != address(0));
            }
            function register(uint256 key, address endpoint) external onlyRole(DEFAULT_ADMIN_ROLE) {
                registry[key] = endpoint;
            }
        }
        """,
        encoding="utf-8",
    )
    from cydra.models import ModifierModel
    from cydra.solidity_model import parse_solidity
    modifier = ModifierModel(
        "onlyRole",
        (ParameterModel("role", "bytes32"),),
        "require(hasRole(role, msg.sender)); _;",
    )
    contract = next(item for item in parse_solidity(source) if item.name == "Target")
    contract = replace(contract, modifiers=(modifier,))
    function = next(item for item in contract.functions if item.name == "run")
    readiness = inspect_execution_readiness(contract, function)
    candidate = next(
        item for item in readiness.state_setup_candidates
        if item.subject == "register"
    )
    assert candidate.status == "unresolved"
    assert "authorization" in candidate.detail


def test_readiness_resolves_modifier_body_without_inventing_role_identity():
    modifier = ModifierModel(
        "onlyRole",
        (ParameterModel("role", "bytes32"),),
        "require(hasRole(role, msg.sender)); _;",
    )
    function = FunctionModel(
        "register",
        "external",
        ("onlyRole",),
        ("registry",),
        (),
        10,
        modifier_invocations=(("onlyRole", ("DEFAULT_ADMIN_ROLE",)),),
    )
    model = ContractModel(
        "Target",
        "/tmp/Target.sol",
        (function,),
        modifiers=(modifier,),
    )

    readiness = inspect_execution_readiness(model, function)
    requirement = readiness.caller_requirements[0]

    assert requirement.subject == "onlyRole(DEFAULT_ADMIN_ROLE)"
    assert "resolved modifier body establishes caller authorization semantics" in requirement.detail
    assert "legitimate role-establishment transition" in requirement.detail


def test_inherited_modifier_authorization_resolves_through_dependency_graph(tmp_path):
    root = tmp_path / "target"
    (root / "lib" / "access-control" / "contracts").mkdir(parents=True)
    (root / "contracts").mkdir(parents=True)
    (root / "contracts" / "Target.sol").write_text(
        'import "./Base.sol";\n'
        'contract Target is Base {}\n',
        encoding="utf-8",
    )
    (root / "contracts" / "Base.sol").write_text(
        'import "@access/contracts/AccessControlLike.sol";\n'
        'abstract contract Base is AccessControlLike {\n'
        '    function register(uint256 key) external onlyRole(DEFAULT_ADMIN_ROLE) {}\n'
        '}\n',
        encoding="utf-8",
    )
    (root / "lib" / "access-control" / "contracts" / "AccessControlLike.sol").write_text(
        'abstract contract AccessControlLike {\n'
        '    modifier onlyRole(bytes32 role) { require(hasRole(role, msg.sender)); _; }\n'
        '}\n',
        encoding="utf-8",
    )

    from cydra.solidity_model import parse_solidity
    contract = next(item for item in parse_solidity(root / "contracts" / "Target.sol") if item.name == "Target")
    inherited = next(item for item in contract.inherited_functions if item.name == "register")
    readiness = inspect_execution_readiness(contract, inherited)

    assert inherited.modifier_invocations == (("onlyRole", ("DEFAULT_ADMIN_ROLE",)),)
    requirement = next(item for item in readiness.caller_requirements if item.kind == "caller_role")
    assert requirement.status == "required"
    assert "resolved modifier body establishes caller authorization semantics" in requirement.detail

def test_constructor_established_role_satisfies_inherited_only_role_for_deployer(tmp_path: Path) -> None:
    access = tmp_path / "AccessControl.sol"
    access.write_text(
        """
        abstract contract AccessControl {
            modifier onlyRole(bytes32 role) {
                require(hasRole(role, msg.sender));
                _;
            }
        }
        """,
        encoding="utf-8",
    )
    base = tmp_path / "Base.sol"
    base.write_text(
        """
        import "./AccessControl.sol";
        contract Base is AccessControl {
            constructor() {
                _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
            }
        }
        """,
        encoding="utf-8",
    )
    target = tmp_path / "Target.sol"
    target.write_text(
        """
        import "./Base.sol";
        contract Target is Base {
            function register(uint256 id, address action)
                external
                onlyRole(DEFAULT_ADMIN_ROLE)
            {}
        }
        """,
        encoding="utf-8",
    )

    contract = parse_solidity(target)[0]
    function = contract.functions[0]
    requirements = _caller_requirements(function, contract)

    assert requirements
    assert requirements[0].status == "constraint"
    assert "deployment caller" in requirements[0].detail

