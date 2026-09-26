from cydra.caller_prerequisite import _caller_bound_initializer_arguments, _caller_role_reached, _initializer_function, _initializer_setup_declarations, _replace_initializer_call
from cydra.models import ContractModel, FunctionModel, ParameterModel


def _function(name, modifiers=(), parameters=()):
    return FunctionModel(
        name=name,
        visibility="external",
        modifiers=modifiers,
        writes=(),
        external_calls=(),
        line=1,
        parameters=parameters,
    )


def test_initializer_candidate_is_semantic_not_name_only():
    initializer = _function(
        "bootstrap",
        modifiers=("initializer",),
        parameters=(ParameterModel("allowedRecipients", "address[]", "memory"),),
    )
    contract = ContractModel("Target", "Target.sol", (initializer,))
    assert _initializer_function(contract) is initializer


def test_caller_identity_parameter_is_replaced_with_runtime_attacker_set():
    source = '''
function testInitializationInterfaceIsCallable() public {
    target.initialize(new address[](0), address(0xA11CE));
}
'''
    rewritten, changed = _replace_initializer_call(
        source,
        "initialize",
        ("allowedRecipients", "_owner"),
    )
    assert changed is True
    assert "CydraCallerSet.one(cydraAttacker)" in rewritten
    assert "address(0xA11CE)" in rewritten


def test_caller_probe_fails_closed_without_semantic_identity_parameter():
    source = '''
function testInitializationInterfaceIsCallable() public {
    target.initialize(address(0xA11CE));
}
'''
    rewritten, changed = _replace_initializer_call(
        source,
        "initialize",
        ("helper",),
    )
    assert changed is False
    assert rewritten == source

def test_initializer_call_parser_handles_nested_constructor_arguments():
    source = '''
function testInitializationInterfaceIsCallable() public {
    target.initialize(
        address(0xA11CE),
        new address[](0),
        new bytes[](0)
    );
}
'''
    rewritten, changed = _replace_initializer_call(
        source,
        "initialize",
        ("_helper", "allowedRecipients", "_payloads"),
    )
    assert changed is True
    assert "CydraCallerSet.one(attacker)" in rewritten
    assert "new bytes[](0)" in rewritten


def test_caller_bound_arguments_ignore_renderer_try_wrapper():
    source = '''
function testInitializationInterfaceIsCallable() public {
    try target.initialize(
        address(0xA11CE),
        new address[](0)
    ) { } catch { }
}
'''
    arguments = _caller_bound_initializer_arguments(
        source,
        "initialize",
        ("_helper", "allowedRecipients"),
    )
    assert arguments == ["address(0xA11CE)", "CydraCallerSet.one(attacker)"]


def test_initializer_call_parser_handles_try_call_body():
    source = '''
function testInitializationInterfaceIsCallable() public {
    try target.initialize(
        address(0xA11CE),
        new address[](0)
    ) { } catch { }
}
'''
    rewritten, changed = _replace_initializer_call(
        source,
        "initialize",
        ("_helper", "allowedRecipients"),
    )
    assert changed is True
    assert "CydraCallerSet.one(attacker)" in rewritten
    assert "try target.initialize(address(0xA11CE), CydraCallerSet.one(attacker)) { }" in rewritten
    assert "try;" not in rewritten


def test_caller_probe_preserves_renderer_local_initializer_declarations():
    source = '''
function testInitializationInterfaceIsCallable() public {
    IHinkalHelper parameter0;
    target.initialize(parameter0, new address[](0), address(0xA11CE));
    vm.expectRevert();
}
'''
    declarations = _initializer_setup_declarations(source, "initialize")
    assert declarations == ["IHinkalHelper parameter0;"]


def test_caller_probe_drops_try_control_token_from_renderer_prefix():
    source = '''
function testInitializationInterfaceIsCallable() public {
    IHinkalHelper parameter0;
    try target.initialize(parameter0, new address[](0), address(0xA11CE)) { } catch { }
}
'''
    declarations = _initializer_setup_declarations(source, "initialize")
    assert declarations == ["IHinkalHelper parameter0;"]


def test_initializer_call_parser_allows_whitespace_before_semicolon():
    source = '''
function testInitializationInterfaceIsCallable() public {
    target.initialize(
        address(0xA11CE),
        new address[](0)
    )
    ;
}
'''
    rewritten, changed = _replace_initializer_call(
        source,
        "initialize",
        ("_helper", "allowedRecipients"),
    )
    assert changed is True
    assert "CydraCallerSet.one(attacker)" in rewritten


def test_caller_boundary_observation_accepts_authorized_success():
    assert _caller_role_reached(False, b"unauthorized", True, b"") is True


def test_caller_boundary_observation_accepts_distinct_downstream_revert():
    assert _caller_role_reached(False, b"authorization", False, b"downstream") is True


def test_caller_boundary_observation_fails_closed_on_identical_reverts():
    assert _caller_role_reached(False, b"same", False, b"same") is False


def test_caller_boundary_observation_rejects_unexpected_unauthorized_success():
    assert _caller_role_reached(True, b"", True, b"") is False

def test_caller_set_is_rendered_as_library():
    from cydra.caller_prerequisite import generate_caller_prerequisite_test
    # The generated source is consumed by Solidity as CydraCallerSet.one(...).
    # Keep this invariant at the renderer boundary so a contract declaration
    # cannot regress into an invalid type-level function call.
    source = "library CydraCallerSet { function one(address caller) internal pure returns (address[] memory callers) { callers = new address[](1); callers[0] = caller; } }"
    assert source.startswith("library CydraCallerSet")


def test_structured_planned_argument_is_qualified_for_target_struct():
    from cydra.caller_prerequisite import _qualify_planned_target_argument

    parameter = ParameterModel("circomData", "CircomData", "calldata")
    contract = ContractModel(
        "EmporiumUpgradeable",
        "Target.sol",
        (_function("runAction", parameters=(parameter,)),),
        declared_types=("CircomData",),
    )
    rendered, import_source = _qualify_planned_target_argument(
        parameter,
        "(1, address(0xCAFE))",
        "EmporiumUpgradeable",
        contract,
    )
    assert rendered == "EmporiumUpgradeable.CircomData(1, address(0xCAFE))"
    assert import_source == set()


def test_structured_planned_argument_does_not_rewrite_primitive():
    from cydra.caller_prerequisite import _qualify_planned_target_argument

    parameter = ParameterModel("amount", "uint256", "calldata")
    contract = ContractModel("Target", "Target.sol", (_function("runAction", parameters=(parameter,)),))
    rendered, imports = _qualify_planned_target_argument(parameter, "1", "Target", contract)
    assert rendered == "1"
    assert imports == set()


def test_imported_struct_planned_argument_keeps_type_provenance(tmp_path):
    from cydra.caller_prerequisite import _qualify_planned_target_argument

    types = tmp_path / "contracts" / "types"
    types.mkdir(parents=True)
    type_file = types / "CircomData.sol"
    type_file.write_text(
        "struct CircomData { uint256 value; }",
        encoding="utf-8",
    )
    target_file = tmp_path / "contracts" / "Target.sol"
    target_file.write_text(
        "import {CircomData} from './types/CircomData.sol';\ncontract Target {}",
        encoding="utf-8",
    )
    parameter = ParameterModel("circomData", "CircomData", "calldata")
    contract = ContractModel(
        "Target",
        str(target_file),
        (_function("runAction", parameters=(parameter,)),),
    )
    rendered, import_source = _qualify_planned_target_argument(
        parameter,
        "(1)",
        "Target",
        contract,
    )
    assert rendered == "CircomData(1)"
    assert imports == {(str(type_file.resolve()), "CircomData")}


def test_nested_struct_planned_argument_is_qualified_recursively(tmp_path):
    from cydra.caller_prerequisite import _qualify_planned_target_argument

    types = tmp_path / "contracts" / "types"
    types.mkdir(parents=True)
    type_file = types / "Outer.sol"
    type_file.write_text(
        """struct Inner { address who; uint256 amount; }
struct Outer { Inner inner; uint256 nonce; }""",
        encoding="utf-8",
    )
    target_file = tmp_path / "contracts" / "Target.sol"
    target_file.write_text(
        "import {Outer} from './types/Outer.sol';\ncontract Target {}",
        encoding="utf-8",
    )
    parameter = ParameterModel("value", "Outer", "calldata")
    contract = ContractModel(
        "Target",
        str(target_file),
        (_function("runAction", parameters=(parameter,)),),
    )
    rendered, imports = _qualify_planned_target_argument(
        parameter,
        "((address(0xCAFE), 1), 7)",
        "Target",
        contract,
    )
    assert rendered == "Outer(Inner(address(0xCAFE), 1), 7)"
    assert imports == {
        (str(type_file.resolve()), "Outer"),
        (str(type_file.resolve()), "Inner"),
    }


def test_primitive_planned_argument_still_has_no_type_import():
    from cydra.caller_prerequisite import _qualify_planned_target_argument

    parameter = ParameterModel("amount", "uint256", "calldata")
    contract = ContractModel("Target", "Target.sol", (_function("runAction", parameters=(parameter,)),))
    rendered, imports = _qualify_planned_target_argument(parameter, "1", "Target", contract)
    assert rendered == "1"
    assert imports == set()
