from cydra.scope import ScopePolicy, ScopeRule, ScopeState, ScopeViolation
from cydra.system_model import Node, SystemModel


def test_scope_is_fail_closed_for_unknown_targets():
    policy = ScopePolicy(rules=[ScopeRule("allowed/*", ScopeState.IN_SCOPE)])
    assert policy.decide("allowed/Target.sol").allowed_for_active_testing
    assert not policy.decide("unknown/Target.sol").allowed_for_active_testing


def test_scope_blocks_active_testing_outside_scope():
    policy = ScopePolicy(rules=[ScopeRule("blocked/*", ScopeState.OUT_OF_SCOPE)])
    try:
        policy.require_active_testing("blocked/Target.sol")
    except ScopeViolation as exc:
        assert exc.decision.state is ScopeState.OUT_OF_SCOPE
    else:
        raise AssertionError("out-of-scope target was not blocked")


def test_canonical_system_model_preserves_provenance_and_graph_structure():
    model = SystemModel()
    model.add_node(Node("contract:C", "contract", "C", {"source": "solidity_model"}))
    model.add_node(Node("function:C:f", "function", "f", {"source": "solidity_model"}))
    model.connect("function:C:f", "defined_in", "contract:C", provenance="solidity_model")
    assert model.neighbors("function:C:f", "defined_in") == ["contract:C"]
    assert model.validate() == []
