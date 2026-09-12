"""Conservative hypothesis belief updates from explicit observations."""
from __future__ import annotations
from .hypotheses import BeliefUpdate, Hypothesis, update_hypothesis
from .invariants import CandidateVerification, VerificationEvidence

def apply_verification(hypothesis: Hypothesis, verification: CandidateVerification, evidence: tuple[VerificationEvidence, ...]) -> tuple[Hypothesis, BeliefUpdate]:
    return update_hypothesis(hypothesis, verification, evidence)
