"""Evidence-grounded diagnostics for deciding whether an investigation is ready.

This layer does not predict vulnerability likelihood. It measures whether CYDRA has
sufficient evidence and a sufficiently challenged model to make a defensible claim.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .system_model import SystemModel


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


def assess_system_model_readiness(model: SystemModel) -> InvestigationReadiness:
    """Derive readiness dimensions from canonical graph state.

    This is intentionally conservative: missing graph evidence lowers readiness
    instead of being interpreted as proof that the target is safe.
    """
    hypotheses = [node for node in model.nodes.values() if node.kind == "hypothesis"]
    evidence = [node for node in model.nodes.values() if node.kind == "evidence"]
    observations = [node for node in model.nodes.values() if node.kind == "observation"]
    contradictions = [
        node for node in evidence
        if node.attributes.get("contradiction") is True
    ]

    if not hypotheses:
        evidence_coverage = 0.0
        hypothesis_coverage = 0.0
    else:
        evidence_bound = 0
        tested = 0
        for hypothesis in hypotheses:
            hid = hypothesis.node_id
            has_evidence = any(
                edge.target == hid
                and edge.source in model.nodes
                and model.nodes[edge.source].kind == "evidence"
                and edge.relation in {"supports", "contradicts", "informs"}
                for edge in model.edges
            )
            has_completed_test = any(
                edge.target == hid
                and edge.relation == "tests"
                and model.nodes.get(edge.source, None) is not None
                and model.nodes[edge.source].attributes.get("executed") is True
                for edge in model.edges
            )
            evidence_bound += int(has_evidence)
            tested += int(has_completed_test)
        evidence_coverage = evidence_bound / len(hypotheses)
        hypothesis_coverage = tested / len(hypotheses)

    confidence_values = [
        float(edge.attributes["confidence"])
        for edge in model.edges
        if edge.attributes.get("evidence_backed")
        and isinstance(edge.attributes.get("confidence"), (int, float))
    ]
    invariant_confidence = [
        float(node.attributes["confidence"])
        for node in model.nodes.values()
        if node.kind == "invariant"
        and isinstance(node.attributes.get("confidence"), (int, float))
    ]
    all_confidence = confidence_values + invariant_confidence
    model_confidence = sum(all_confidence) / len(all_confidence) if all_confidence else 0.0

    if not contradictions:
        contradiction_clearance = 1.0
    else:
        cleared = 0
        for contradiction in contradictions:
            competing = contradiction.attributes.get("competing_hypothesis_ids", ())
            if competing and all(
                model.nodes.get(hid, None) is not None
                and model.nodes[hid].attributes.get("state") != "unresolved"
                for hid in competing
            ):
                cleared += 1
        contradiction_clearance = cleared / len(contradictions)

    if not observations:
        experiment_validity = 0.0
    else:
        valid = sum(
            int(observation.attributes.get("executed") is True and observation.attributes.get("status") == "completed")
            for observation in observations
        )
        experiment_validity = valid / len(observations)

    reasons: list[str] = []
    if not hypotheses:
        reasons.append("no canonical hypotheses have been registered")
    if evidence and not observations:
        reasons.append("evidence exists without a corresponding executed observation")

    return assess_investigation_readiness(
        evidence_coverage=evidence_coverage,
        model_confidence=model_confidence,
        hypothesis_coverage=hypothesis_coverage,
        contradiction_clearance=contradiction_clearance,
        experiment_validity=experiment_validity,
        unresolved_reasons=tuple(reasons),
    )
