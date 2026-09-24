from cydra.execution_readiness import ExecutionReadiness, ExecutionRequirement, SetupAction
from cydra.prerequisite_graph import build_prerequisite_graph, can_enter_security_experiment


def test_discovered_requirement_is_not_verified():
    readiness = ExecutionReadiness(
        contract="Target",
        execution_requirements=(
            ExecutionRequirement("execution_value_producer", "balance", "producer", "discovered"),
        ),
    )
    graph = build_prerequisite_graph(readiness)
    assert graph.unresolved
    assert not can_enter_security_experiment(graph)


def test_constructible_setup_is_not_verified():
    readiness = ExecutionReadiness(contract="Target")
    graph = build_prerequisite_graph(
        readiness,
        (SetupAction("seedBalance", "owner", ("Target:balance",)),),
    )
    assert graph.nodes[0].status == "constructible"
    assert graph.nodes[0].verification == "postcondition_required"
    assert not can_enter_security_experiment(graph)


def test_explicit_verification_is_required():
    readiness = ExecutionReadiness(
        contract="Target",
        state_requirements=(
            ExecutionRequirement("state_predicate", "balance > 0", "test", "verified"),
        ),
    )
    graph = build_prerequisite_graph(readiness)
    assert graph.verified
    assert not graph.unresolved
    assert can_enter_security_experiment(graph)


def test_unknown_status_fails_closed():
    readiness = ExecutionReadiness(
        contract="Target",
        caller_requirements=(
            ExecutionRequirement("caller_role", "admin", "model", "unknown"),
        ),
    )
    graph = build_prerequisite_graph(readiness)
    assert graph.unresolved
    assert not can_enter_security_experiment(graph)
