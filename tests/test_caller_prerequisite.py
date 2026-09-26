from cydra.caller_prerequisite import _caller_bound_initializer_arguments, _initializer_function, _initializer_setup_declarations, _replace_initializer_call
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
    assert "CydraCallerSet.one(attacker)" in rewritten
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
    assert "try target.initialize(address(0xA11CE), CydraCallerSet.one(attacker)) { }" in rewritten\n    assert "try;" not in rewritten


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
