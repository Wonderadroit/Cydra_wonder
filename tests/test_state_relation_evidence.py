from pathlib import Path

from cydra.foundry import ExecutionResult
from cydra.models import ContractModel, FunctionModel
from cydra.state_relation_observation import plan_state_relation_observations
from cydra.state_relation_evidence import (
    evidence_records_from_relation_execution,
    relation_observation_evidence_id,
)


def _plan(tmp_path: Path):
    source = tmp_path / "Target.sol"
    source.write_text(
        "contract Target { uint256 public counter; "
        "function bump() external { counter += 1; } }",
        encoding="utf-8",
    )
    model = ContractModel(
        "Target",
        str(source),
        (FunctionModel("bump", "external", (), ("counter",), (), 2),),
        state_variables=("counter",),
    )
    return plan_state_relation_observations(model, model.functions[0])[0]


def _execution(status="PASS", executed=True, tests_run=1, tests_failed=0):
    return ExecutionResult(
        experiment_id="X-REL",
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


def test_relation_evidence_requires_passing_executed_assertion(tmp_path: Path):
    plan = _plan(tmp_path)
    evidence = evidence_records_from_relation_execution(
        "X-REL", ((0, plan),), _execution()
    )
    assert len(evidence) == 1
    assert evidence[0].evidence_id == relation_observation_evidence_id("X-REL", plan, 0)
    assert evidence[0].expression == "after(counter) == before(counter) + 1"
    assert evidence[0].step_index == 0


def test_relation_evidence_fails_closed_on_failed_execution(tmp_path: Path):
    plan = _plan(tmp_path)
    assert evidence_records_from_relation_execution(
        "X-REL", ((0, plan),), _execution(status="FAIL")
    ) == ()


def test_relation_evidence_does_not_accept_unexecuted_or_empty_tests(tmp_path: Path):
    plan = _plan(tmp_path)
    assert evidence_records_from_relation_execution(
        "X-REL", ((0, plan),), _execution(executed=False)
    ) == ()
    assert evidence_records_from_relation_execution(
        "X-REL", ((0, plan),), _execution(tests_run=0)
    ) == ()


def test_relation_evidence_uses_explicit_ordered_step_indexes(tmp_path: Path):
    plan = _plan(tmp_path)
    first = relation_observation_evidence_id("X-REL-SEQUENCE", plan, 0)
    second = relation_observation_evidence_id("X-REL-SEQUENCE", plan, 2)
    assert first != second
    evidence = evidence_records_from_relation_execution(
        "X-REL-SEQUENCE", ((0, plan), (2, plan)), _execution()
    )
    assert [item.evidence_id for item in evidence] == [first, second]
    assert [item.step_index for item in evidence] == [0, 2]


def test_relation_violation_evidence_requires_generated_assertion_failure(tmp_path: Path):
    plan = _plan(tmp_path)
    from cydra.state_relation_evidence import (
        violation_records_from_relation_execution,
        relation_violation_evidence_id,
    )

    execution = _execution(status="FAIL")
    execution = ExecutionResult(
        experiment_id=execution.experiment_id,
        target=execution.target,
        command=execution.command,
        exit_code=1,
        executed=True,
        tests_run=1,
        tests_failed=1,
        status="FAIL",
        stdout="FAIL: unverified state relation: after(counter) == before(counter) + 1",
        stderr="",
    )
    evidence = violation_records_from_relation_execution(
        "X-REL", ((0, plan),), execution
    )
    assert len(evidence) == 1
    assert evidence[0].kind == "relation_mismatch"
    assert evidence[0].expression == "after(counter) == before(counter) + 1"
    assert evidence[0].evidence_id == relation_violation_evidence_id("X-REL", plan, 0)


def test_relation_violation_evidence_rejects_generic_failure(tmp_path: Path):
    plan = _plan(tmp_path)
    from cydra.state_relation_evidence import violation_records_from_relation_execution

    execution = ExecutionResult(
        experiment_id="X-REL",
        target="Target",
        command=("forge", "test"),
        exit_code=1,
        executed=True,
        tests_run=1,
        tests_failed=1,
        status="FAIL",
        stdout="candidate call reverted: EpochNotFulfilled()",
        stderr="",
    )
    assert violation_records_from_relation_execution(
        "X-REL", ((0, plan),), execution
    ) == ()
