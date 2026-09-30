from cydra.foundry import ExecutionResult
from cydra.prerequisite_graph import PrerequisiteGraph, PrerequisiteNode, apply_observations, can_enter_security_experiment
from cydra.runtime_observation import StateObservationPlan
from cydra.runtime_observation_evidence import observations_from_execution


def _execution(status="PASS", executed=True, tests_run=1, tests_failed=0):
    return ExecutionResult(
        experiment_id="SETUP-001",
        target="Target",
        command=("forge", "test"),
        exit_code=0 if status == "PASS" else 1,
        executed=executed,
        tests_run=tests_run,
        tests_failed=tests_failed,
        status=status,
        stdout="",
        stderr="",
    )


def test_successful_observation_promotes_only_after_execution():
    plan = StateObservationPlan(
        state="epoch",
        getter="target.epoch()",
        expression="target.epoch() > 0",
        predicate="epoch > 0",
        polarity="must_hold",
        source="Target.sol:10",
    )
    graph = PrerequisiteGraph((
        PrerequisiteNode(
            subject="epoch > 0",
            kind="state",
            status="unresolved",
            source="execution_readiness",
        ),
    ))

    observations = observations_from_execution("SETUP-001", (plan,), _execution())
    assert len(observations) == 1
    verified = apply_observations(graph, observations)
    assert verified.nodes[0].status == "verified"
    assert verified.nodes[0].verification.startswith("E-OBS-STATE-")
    assert can_enter_security_experiment(verified)


def test_failed_or_unexecuted_observation_never_promotes():
    plan = StateObservationPlan(
        state="epoch",
        getter="target.epoch()",
        expression="target.epoch() > 0",
        predicate="epoch > 0",
        polarity="must_hold",
        source="Target.sol:10",
    )
    graph = PrerequisiteGraph((
        PrerequisiteNode(
            subject="epoch",
            kind="state",
            status="unresolved",
            source="execution_readiness",
        ),
    ))

    assert observations_from_execution("SETUP-001", (plan,), _execution("FAIL")) == ()
    assert observations_from_execution(
        "SETUP-001", (plan,), _execution("PASS", executed=False)
    ) == ()
    assert graph.nodes[0].status == "unresolved"


def test_observation_id_is_stable():
    plan = StateObservationPlan(
        state="epoch",
        getter="target.epoch()",
        expression="target.epoch() > 0",
        predicate="epoch > 0",
        polarity="must_hold",
        source="Target.sol:10",
    )
    first = observations_from_execution("SETUP-001", (plan,), _execution())[0]
    second = observations_from_execution("SETUP-001", (plan,), _execution())[0]
    assert first.evidence_id == second.evidence_id


def test_internal_mapping_observation_traverses_nested_same_contract_calls(tmp_path):
    source = tmp_path / "Target.sol"
    source.write_text(
        """
        contract Target {
            mapping(address => address) public externalActionMap;

            function transact() external {
                if (true) {
                    _externalTransact();
                }
            }

            function _externalTransact() internal {
                if (true) {
                    require(
                        externalActionMap[msg.sender] == msg.sender &&
                        externalActionMap[msg.sender] != address(0)
                    );
                }
            }
        }
        """,
        encoding="utf-8",
    )
    target = FunctionModel(
        name="transact",
        visibility="external",
        modifiers=(),
        writes=(),
        external_calls=(),
        line=4,
    )
    callee = FunctionModel(
        name="_externalTransact",
        visibility="internal",
        modifiers=(),
        writes=(),
        external_calls=(),
        line=10,
        execution_predicates=(
            "externalActionMap[msg.sender] == msg.sender && externalActionMap[msg.sender] != address(0)",
        ),
    )
    contract = ContractModel(
        name="Target",
        source=str(source),
        functions=(target, callee),
        state_variables=("externalActionMap",),
    )

    from cydra.runtime_observation import plan_public_state_observations

    plans = plan_public_state_observations(contract, target)
    assert any(
        plan.state == "externalActionMap"
        and plan.getter == "target.externalActionMap(msg.sender)"
        for plan in plans
    )

def test_adapter_owned_runtime_dependency_does_not_block_experiment():
    graph = PrerequisiteGraph((
        PrerequisiteNode(
            subject="helper.performSideEffects",
            kind="runtime_dependency",
            status="constructible",
            source="Target.transact",
            capability="INTERNAL_CALL_PROPAGATION",
        ),
        PrerequisiteNode(
            subject="state predicate",
            kind="state",
            status="verified",
            source="runtime_observation",
            capability="STATE_OBSERVATION",
        ),
    ))
    assert can_enter_security_experiment(graph)


def test_constructible_state_setup_still_blocks_experiment():
    graph = PrerequisiteGraph((
        PrerequisiteNode(
            subject="registerExternalAction",
            kind="setup_transition",
            status="constructible",
            source="execution_readiness",
            capability="STATE_SETUP",
        ),
    ))
    assert not can_enter_security_experiment(graph)
\n