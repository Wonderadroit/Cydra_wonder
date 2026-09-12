"""Thin integration bridge from evidence-backed invariants to explicit hypotheses."""
from __future__ import annotations
from .invariant_hypothesis_bridge import InvariantHypothesis, hypotheses_from_verified_invariants, persist_invariant_hypotheses
from .invariant_persistence import persist_invariant_verification
from .invariants import InvariantCandidate, VerificationEvidence, verify_candidate
from .system_model import SystemModel


def verify_and_bind_invariants(model: SystemModel, candidates: tuple[InvariantCandidate, ...], evidence: tuple[VerificationEvidence, ...]) -> tuple[InvariantHypothesis, ...]:
    """Persist candidate verification and emit hypotheses only for explicit support.

    No execution is performed and no unresolved candidate is promoted.
    """
    for candidate in candidates:
        verification = verify_candidate(candidate, evidence)
        persist_invariant_verification(model, candidate, verification)
    hypotheses = hypotheses_from_verified_invariants(model, candidates)
    persist_invariant_hypotheses(model, hypotheses)
    return hypotheses
