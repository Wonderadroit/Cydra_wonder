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
            subject="epoch",
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
