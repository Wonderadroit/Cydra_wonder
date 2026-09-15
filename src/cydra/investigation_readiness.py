"""Evidence-grounded diagnostics for deciding whether an investigation is ready.

This layer does not predict vulnerability likelihood. It measures whether CYDRA has
sufficient evidence and a sufficiently challenged model to make a defensible claim.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ReadinessState(str, Enum):
    READY = "ready"
    CONDITIONAL = "conditional"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class InvestigationReadiness:
    state: ReadinessState
    score: float
    evidence_coverage: float
    model_confidence: float
    hypothesis_coverage: float
    contradiction_clearance: float
    experiment_validity: float
    unresolved_reasons: tuple[str, ...]
    recommended_next_tests: tuple[str, ...]


def assess_investigation_readiness(
    *,
    evidence_coverage: float,
    model_confidence: float,
    hypothesis_coverage: float,
    contradiction_clearance: float,
    experiment_validity: float,
    unresolved_reasons: tuple[str, ...] = (),
    recommended_next_tests: tuple[str, ...] = (),
) -> InvestigationReadiness:
    """Assess investigation readiness from explicit evidence dimensions.

    Inputs are normalized to [0, 1]. The score is an explainable readiness measure,
    not a probability that a vulnerability exists or will be found.
    """
    values = {
        "evidence_coverage": evidence_coverage,
        "model_confidence": model_confidence,
        "hypothesis_coverage": hypothesis_coverage,
        "contradiction_clearance": contradiction_clearance,
        "experiment_validity": experiment_validity,
    }
    if any(not 0.0 <= value <= 1.0 for value in values.values()):
        raise ValueError("readiness dimensions must be between 0 and 1")

    score = sum(values.values()) / len(values)
    reasons = list(unresolved_reasons)
    tests = list(recommended_next_tests)

    if contradiction_clearance < 1.0 and "unresolved contradictions" not in reasons:
        reasons.append("unresolved contradictions")
        if "challenge competing system explanations" not in tests:
            tests.append("challenge competing system explanations")
    if evidence_coverage < 1.0 and "evidence coverage is incomplete" not in reasons:
        reasons.append("evidence coverage is incomplete")
    if hypothesis_coverage < 1.0 and "relevant behavior remains untested" not in reasons:
        reasons.append("relevant behavior remains untested")
    if experiment_validity < 1.0 and "experiment validity is incomplete" not in reasons:
        reasons.append("experiment validity is incomplete")
    if model_confidence < 1.0 and "system model remains uncertain" not in reasons:
        reasons.append("system model remains uncertain")

    if experiment_validity == 0.0 or model_confidence < 0.5 or contradiction_clearance < 0.5:
        state = ReadinessState.BLOCKED
    elif score >= 0.9 and not reasons:
        state = ReadinessState.READY
    else:
        state = ReadinessState.CONDITIONAL

    return InvestigationReadiness(
        state,
        round(score, 6),
        evidence_coverage,
        model_confidence,
        hypothesis_coverage,
        contradiction_clearance,
        experiment_validity,
        tuple(reasons),
        tuple(tests),
    )
