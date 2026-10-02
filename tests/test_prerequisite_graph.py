from cydra.execution_readiness import ExecutionReadiness, ExecutionRequirement, SetupAction
from cydra.prerequisite_graph import (
    PrerequisiteObservation,
    apply_observations,
    build_prerequisite_graph,
    can_enter_security_experiment,
)


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



def test_no_prerequisites_is_executable():
    graph = build_prerequisite_graph(ExecutionReadiness(contract="Target"))
    assert graph.nodes == ()
    assert can_enter_security_experiment(graph)



def test_matching_runtime_observation_promotes_prerequisite():
    readiness = ExecutionReadiness(
        contract="Target",
        state_requirements=(
            ExecutionRequirement("state_predicate", "balance > 0", "model", "required"),
        ),
    )
    graph = build_prerequisite_graph(readiness)
    verified = apply_observations(
        graph,
        (PrerequisiteObservation("state_predicate", "balance > 0", "true", "true", "E-SETUP-1"),),
    )
    assert verified.verified[0].verification == "E-SETUP-1"
    assert can_enter_security_experiment(verified)


def test_mismatching_runtime_observation_blocks_prerequisite():
    readiness = ExecutionReadiness(
        contract="Target",
        state_requirements=(
            ExecutionRequirement("state_predicate", "balance > 0", "model", "required"),
        ),
    )
    graph = build_prerequisite_graph(readiness)
    blocked = apply_observations(
        graph,
        (PrerequisiteObservation("state_predicate", "balance > 0", "true", "false", "E-SETUP-2"),),
    )
    assert blocked.nodes[0].status == "blocked"
    assert not can_enter_security_experiment(blocked)



def test_observation_kind_mismatch_does_not_promote():
    readiness = ExecutionReadiness(
        contract="Target",
        state_requirements=(
            ExecutionRequirement("state_predicate", "balance > 0", "model", "required"),
        ),
    )
    graph = build_prerequisite_graph(readiness)
    unchanged = apply_observations(
        graph,
        (PrerequisiteObservation("execution_predicate", "balance > 0", "true", "true", "E-SETUP-3"),),
    )
    assert unchanged.unresolved
    assert not can_enter_security_experiment(unchanged)


def test_experiment_constraint_does_not_block_security_entry():
    readiness = ExecutionReadiness(
        contract="Target",
        execution_requirements=(
            ExecutionRequirement(
                "execution_predicate",
                "amount > 0",
                "test:body",
                "constraint",
            ),
        ),
    )
    graph = build_prerequisite_graph(readiness)
    assert graph.nodes[0].status == "constraint"
    assert graph.unresolved == ()
    assert can_enter_security_experiment(graph)


def test_verified_prerequisite_still_blocks_until_verified():
    readiness = ExecutionReadiness(
        contract="Target",
        execution_requirements=(
            ExecutionRequirement(
                "execution_predicate",
                "storedBalance > 0",
                "test:body",
                "required",
            ),
        ),
    )
    graph = build_prerequisite_graph(readiness)
    assert graph.unresolved
    assert not can_enter_security_experiment(graph)


def test_prerequisite_nodes_expose_generic_capability_clusters():
    readiness = ExecutionReadiness(
        contract="Target",
        caller_requirements=(
            ExecutionRequirement("caller_role", "admin", "model", "required"),
        ),
        state_requirements=(
            ExecutionRequirement("state_predicate", "balance > 0", "model", "required"),
        ),
    )
    graph = build_prerequisite_graph(readiness)
    assert graph.nodes[0].capability == "CALLER_CONSTRUCTION"
    assert graph.nodes[1].capability == "STATE_OBSERVATION"
    assert graph.capability_clusters == {
        "CALLER_CONSTRUCTION": 1,
        "STATE_OBSERVATION": 1,
    }


def test_predicate_category_preserves_specific_capability():
    readiness = ExecutionReadiness(
        contract="Target",
        execution_requirements=(
            ExecutionRequirement(
                "execution_predicate",
                "verifyProof(...)",
                "target:body",
                "required",
                category="cryptographic_witness",
            ),
        ),
    )
    graph = build_prerequisite_graph(readiness)
    assert graph.nodes[0].capability == "CRYPTOGRAPHIC_WITNESS"
    assert graph.capability_clusters == {"CRYPTOGRAPHIC_WITNESS": 1}


def test_state_observation_verifies_generic_setup_transition_postcondition():
    readiness = ExecutionReadiness(
        contract="Target",
        state_requirements=(
            ExecutionRequirement(
                "state_predicate",
                "allowedRecipient != address(0)",
                "model",
                "required",
            ),
        ),
    )
    action = SetupAction(
        "setRecipient",
        None,
        ("Target:act:allowedRecipient",),
    )
    graph = build_prerequisite_graph(readiness, (action,))
    verified = apply_observations(
        graph,
        (
            PrerequisiteObservation(
                "state",
                "allowedRecipient != address(0)",
                "true",
                "true",
                "E-OBS-STATE-1",
            ),
        ),
    )
    setup = next(node for node in verified.nodes if node.kind == "setup_transition")
    assert setup.status == "verified"
    assert setup.verification == "E-OBS-STATE-1"
    assert can_enter_security_experiment(verified)


def test_state_observation_does_not_verify_unrelated_setup_transition():
    readiness = ExecutionReadiness(
        contract="Target",
        state_requirements=(
            ExecutionRequirement(
                "state_predicate",
                "allowedRecipient != address(0)",
                "model",
                "required",
            ),
        ),
    )
    action = SetupAction("unrelated", None, ("Target:act:otherState",))
    graph = build_prerequisite_graph(readiness, (action,))
    verified = apply_observations(
        graph,
        (
            PrerequisiteObservation(
                "state",
                "allowedRecipient != address(0)",
                "true",
                "true",
                "E-OBS-STATE-2",
            ),
        ),
    )
    setup = next(node for node in verified.nodes if node.kind == "setup_transition")
    assert setup.status == "constructible"
    assert not can_enter_security_experiment(verified)


def test_state_observation_matches_model_state_predicate_kind():
    readiness = ExecutionReadiness(
        contract="Target",
        state_requirements=(
            ExecutionRequirement(
                "state_predicate",
                "balance > 0",
                "model",
                "required",
            ),
        ),
    )
    graph = build_prerequisite_graph(readiness)
    verified = apply_observations(
        graph,
        (
            PrerequisiteObservation(
                "state",
                "balance > 0",
                "true",
                "true",
                "E-OBS-STATE-3",
            ),
        ),
    )
    assert verified.nodes[0].status == "verified"
