"""Explicit boundary between canonical reasoning states and legacy labels."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .causal_verification import CausalVerificationState
from .hypotheses import HypothesisState


class LegacyClassification(str, Enum):
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    PROPOSED = "proposed"
    NOT_CONFIRMED = "not_confirmed"


class ReasoningStage(str, Enum):
    PROPOSED = "proposed"
    SUPPORTED = "supported"
    EXPERIMENTALLY_SUPPORTED = "experimentally_supported"
    CAUSALLY_ESTABLISHED = "causally_established"
    FINDING = "finding"
    REJECTED = "rejected"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class ClassificationReconciliation:
    hypothesis_id: str
    reasoning_stage: ReasoningStage
    legacy_classification: LegacyClassification
    execution_boundary: str | None
    rationale: str


def reconcile_classification(
    hypothesis_id: str,
    hypothesis_state: HypothesisState,
    *,
    causal_state: CausalVerificationState | None = None,
    experimentally_supported: bool = False,
    finding_ready: bool = False,
    execution_boundary: str | None = None,
) -> ClassificationReconciliation:
    """Map canonical epistemic state to legacy labels without collapsing stages."""
    if not hypothesis_id.strip():
        raise ValueError("hypothesis_id must not be empty")
    if finding_ready and causal_state is not CausalVerificationState.VERIFIED:
        raise ValueError("finding classification requires verified causal establishment")
    if finding_ready:
        stage = ReasoningStage.FINDING
        classification = LegacyClassification.CONFIRMED
        rationale = "finding gate established the canonical causal and reproducibility requirements"
    elif causal_state is CausalVerificationState.VERIFIED:
        stage = ReasoningStage.CAUSALLY_ESTABLISHED
        classification = LegacyClassification.CONFIRMED
        rationale = "persisted causal chain was explicitly verified"
    elif causal_state is CausalVerificationState.REJECTED or hypothesis_state is HypothesisState.CONTRADICTED:
        stage = ReasoningStage.REJECTED
        classification = LegacyClassification.REJECTED
        rationale = "canonical reasoning contains explicit contradiction or rejected causal verification"
    elif experimentally_supported:
        stage = ReasoningStage.EXPERIMENTALLY_SUPPORTED
        classification = LegacyClassification.PROPOSED
        rationale = "experiment supports the hypothesis but causal establishment has not been verified"
    elif hypothesis_state is HypothesisState.SUPPORTED:
        stage = ReasoningStage.SUPPORTED
        classification = LegacyClassification.PROPOSED
        rationale = "model-level evidence supports the hypothesis; this is not yet experimental or causal confirmation"
    elif execution_boundary:
        stage = ReasoningStage.UNRESOLVED
        classification = LegacyClassification.NOT_CONFIRMED
        rationale = "execution reached an epistemic boundary; classification is not confirmation or rejection"
    else:
        stage = ReasoningStage.UNRESOLVED
        classification = LegacyClassification.PROPOSED
        rationale = "hypothesis remains unresolved and therefore cannot be confirmed"

    return ClassificationReconciliation(hypothesis_id, stage, classification, execution_boundary, rationale)
