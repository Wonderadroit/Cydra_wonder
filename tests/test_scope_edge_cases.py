from cydra.scope import ScopePolicy, ScopeRule, ScopeState, ScopeViolation


def test_empty_conditional_rule_fails_closed():
    policy = ScopePolicy(rules=[ScopeRule("conditional/*", ScopeState.CONDITIONAL)])
    decision = policy.decide("conditional/Target.sol")
    assert not decision.allowed_for_active_testing
    try:
        policy.require_active_testing("conditional/Target.sol")
    except ScopeViolation:
        pass
    else:
        raise AssertionError("empty conditional scope rule allowed active testing")
