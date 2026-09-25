from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .foundry import ExecutionResult
from .state_relation_observation import StateRelationObservationPlan


@dataclass(frozen=True)
class StateRelationObservationEvidence:
    """Immutable evidence that a modeled state transition passed its runtime assertion."""

    evidence_id: str
    kind: str
    state: str
    relation: str
    experiment_id: str
    expression: str
    source: str
    step_index: int = 0


@dataclass(frozen=True)
class StateRelationViolationEvidence:
    """Immutable evidence that a generated relation assertion actually failed."""

    evidence_id: str
    kind: str
    state: str
    relation: str
    experiment_id: str
    expression: str
    source: str
    step_index: int = 0


def relation_observation_evidence_id(
    experiment_id: str, plan: StateRelationObservationPlan, step_index: int = 0
) -> str:
    material = (
        f"{experiment_id}|step:{step_index}|{plan.state}|"
        f"{plan.relation.function}|{plan.relation.expression}|{plan.getter}"
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"E-OBS-REL-{digest}"


def relation_violation_evidence_id(
    experiment_id: str, plan: StateRelationObservationPlan, step_index: int = 0
) -> str:
    material = (
        f"{experiment_id}|violation|step:{step_index}|{plan.state}|"
        f"{plan.relation.function}|{plan.relation.expression}|{plan.getter}"
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"E-OBS-REL-VIOLATION-{digest}"


def evidence_records_from_relation_execution(
    experiment_id: str,
    plans: tuple[tuple[int, StateRelationObservationPlan], ...],
    execution: ExecutionResult,
) -> tuple[StateRelationObservationEvidence, ...]:
    """Emit relation evidence only after an executed, passing assertion test."""

    if not execution.executed or execution.status != "PASS":
        return ()
    if execution.tests_run < 1 or execution.tests_failed != 0:
        return ()

    return tuple(
        StateRelationObservationEvidence(
            evidence_id=relation_observation_evidence_id(experiment_id, plan, step_index),
            kind="execution",
            state=plan.state,
            relation=plan.relation.function,
            experiment_id=experiment_id,
            expression=plan.relation.expression,
            source=plan.source,
            step_index=step_index,
        )
        for step_index, plan in plans
    )


def violation_records_from_relation_execution(
    experiment_id: str,
    plans: tuple[tuple[int, StateRelationObservationPlan], ...],
    execution: ExecutionResult,
) -> tuple[StateRelationViolationEvidence, ...]:
    """Emit violation evidence only for a real generated relation assertion failure.

    A generic forge failure, revert, compile error, or empty test run is not a
    relation violation. The generated assertion uses a stable diagnostic prefix,
    so only failures containing that prefix are promoted to relation-mismatch
    evidence. The result remains evidence, not a vulnerability classification.
    """

    if not execution.executed or execution.status != "FAIL":
        return ()
    if execution.tests_run < 1 or execution.tests_failed < 1:
        return ()

    output = f"{execution.stdout}\n{execution.stderr}"
    if "unverified state relation:" not in output:
        return ()

    matched: list[tuple[int, StateRelationObservationPlan]] = []
    for step_index, plan in plans:
        if plan.relation.expression in output:
            matched.append((step_index, plan))
    if not matched:
        return ()

    return tuple(
        StateRelationViolationEvidence(
            evidence_id=relation_violation_evidence_id(experiment_id, plan, step_index),
            kind="relation_mismatch",
            state=plan.state,
            relation=plan.relation.function,
            experiment_id=experiment_id,
            expression=plan.relation.expression,
            source=plan.source,
            step_index=step_index,
        )
        for step_index, plan in matched
    )
