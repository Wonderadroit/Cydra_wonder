"""Dependency-closed invariant reasoning primitives."""
from __future__ import annotations

from .invariants import Invariant, InvariantCandidate, InvariantRegistry, InvariantStatus, VerificationEvidence, CandidateVerification, verify_candidate
from .system_model import SystemModel


def derive_invariant_candidates(model: SystemModel) -> tuple[InvariantCandidate, ...]:
    from .invariants import candidates_from_system_model
    return candidates_from_system_model(model)


def register_inferred_invariants(model: SystemModel, candidates: tuple[InvariantCandidate, ...]) -> InvariantRegistry:
    registry = InvariantRegistry()
    for candidate in candidates:
        registry.add(Invariant(candidate.candidate_id, candidate.statement, InvariantStatus.INFERRED,
                               candidate.source_ids, candidate.confidence,
                               {"evidence_count": str(candidate.evidence_count)}))
    return registry


def verify_invariant_candidate(candidate: InvariantCandidate, evidence: tuple[VerificationEvidence, ...]) -> CandidateVerification:
    return verify_candidate(candidate, evidence)
