from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .foundry import ExecutionResult
from .prerequisite_graph import PrerequisiteObservation
from .runtime_observation import StateObservationPlan


@dataclass(frozen=True)
class RuntimeObservationEvidence:
    """Evidence produced only by a successfully executed runtime assertion."""

    evidence_id: str
    kind: str
    subject: str
    expected: str
    observed: str
    experiment_id: str
    expression: str


def observation_evidence_id(experiment_id: str, plan: StateObservationPlan) -> str:
    """Return a stable provenance ID for one runtime observation."""
    material = f"{experiment_id}|{plan.state}|{plan.predicate}|{plan.expression}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"E-OBS-STATE-{digest}"


def observations_from_execution(
    experiment_id: str,
    plans: tuple[StateObservationPlan, ...],
    execution: ExecutionResult,
) -> tuple[PrerequisiteObservation, ...]:
    """Promote only assertions that actually executed and passed.

    A failed, empty, or unexecuted Foundry run produces no observation. In
    particular, transaction success is never interpreted as state verification.
    """
    if not execution.executed or execution.status != "PASS":
        return ()
    if execution.tests_run < 1 or execution.tests_failed != 0:
        return ()

    observations: list[PrerequisiteObservation] = []
    for plan in plans:
        evidence_id = observation_evidence_id(experiment_id, plan)
        observations.append(
            PrerequisiteObservation(
                kind="state",
                subject=plan.predicate,
                expected="true",
                observed="true",
                evidence_id=evidence_id,
            )
        )
    return tuple(observations)


def evidence_records_from_execution(
    experiment_id: str,
    plans: tuple[StateObservationPlan, ...],
    execution: ExecutionResult,
) -> tuple[RuntimeObservationEvidence, ...]:
    """Expose the same successful observations as immutable provenance records."""
    if not execution.executed or execution.status != "PASS":
        return ()
    if execution.tests_run < 1 or execution.tests_failed != 0:
        return ()

    return tuple(
        RuntimeObservationEvidence(
            evidence_id=observation_evidence_id(experiment_id, plan),
            kind="execution",
            subject=plan.predicate,
            expected="true",
            observed="true",
            experiment_id=experiment_id,
            expression=plan.expression,
        )
        for plan in plans
    )
