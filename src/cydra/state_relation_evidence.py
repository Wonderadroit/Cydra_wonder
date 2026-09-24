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


def relation_observation_evidence_id(
    experiment_id: str, plan: StateRelationObservationPlan
) -> str:
    material = (
        f"{experiment_id}|{plan.state}|{plan.relation.function}|"
        f"{plan.relation.expression}|{plan.getter}"
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"E-OBS-REL-{digest}"


def evidence_records_from_relation_execution(
    experiment_id: str,
    plans: tuple[StateRelationObservationPlan, ...],
    execution: ExecutionResult,
) -> tuple[StateRelationObservationEvidence, ...]:
    """Emit relation evidence only after an executed, passing assertion test.

    A successful transaction without the generated before/after assertion does
    not qualify. This function is deliberately independent from prerequisite
    observations because a transition relation is evidence about a state
    change, not proof that a prerequisite predicate was satisfied.
    """
    if not execution.executed or execution.status != "PASS":
        return ()
    if execution.tests_run < 1 or execution.tests_failed != 0:
        return ()

    return tuple(
        StateRelationObservationEvidence(
            evidence_id=relation_observation_evidence_id(experiment_id, plan),
            kind="execution",
            state=plan.state,
            relation=plan.relation.function,
            experiment_id=experiment_id,
            expression=plan.relation.expression,
            source=plan.source,
        )
        for plan in plans
    )
