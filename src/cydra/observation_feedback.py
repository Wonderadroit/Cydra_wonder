"""Close the observation -> evidence -> hypothesis feedback loop."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .hypotheses import BeliefUpdate, Hypothesis, update_hypothesis
from .invariants import CandidateVerification, VerificationEvidence
from .observation_outcomes import ObservationOutcome


@dataclass(frozen=True)
class ObservationFeedback:
    observation_id: str
    evidence_ids: tuple[str, ...]
    hypothesis_updates: tuple[BeliefUpdate, ...]


def apply_observation_feedback(outcome: ObservationOutcome, verification: CandidateVerification, hypotheses: Iterable[Hypothesis], evidence: Iterable[VerificationEvidence]) -> tuple[Hypothesis, ...]:
    items = tuple(evidence)
    if outcome.outcome_id not in set(verification.evidence_ids):
        raise ValueError("observation outcome evidence is not part of verification")
    return tuple(update_hypothesis(hypothesis, verification, items)[0] for hypothesis in hypotheses)
