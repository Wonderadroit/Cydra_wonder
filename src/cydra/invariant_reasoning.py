"""Dependency-closed invariant reasoning primitives.

This module is deliberately independent of the frozen benchmark runner. It derives
candidate invariants from evidence-backed SystemModel relationships rather than from
vulnerability-class names or hard-coded source patterns.
"""
from __future__ import annotations

from .invariants import (
    Invariant,
    InvariantCandidate,
    InvariantRegistry,
    InvariantStatus,
    VerificationEvidence,
    CandidateVerification,
    verify_candidate,
)
from .system_model import SystemModel


def derive_invariant_candidates(model: SystemModel) -> tuple[InvariantCandidate, ...]:
    """Return conservative candidates backed by canonical graph evidence."""
    from .invariants import candidates_from_system_model
    return candidates_from_system_model(model)


def register_inferred_invariants(
    model: SystemModel, candidates: tuple[InvariantCandidate, ...]
) -> InvariantRegistry:
    registry = InvariantRegistry()
    for candidate in candidates:
        registry.add(Invariant(
            invariant_id=candidate.candidate_id,
            statement=candidate.statement,
            status=InvariantStatus.INFERRED,
            source_ids=candidate.source_ids,
            confidence=candidate.confidence,
            metadata={"evidence_count": str(candidate.evidence_count)},
        ))
    return registry


def verify_invariant_candidate(
    candidate: InvariantCandidate,
    evidence: tuple[VerificationEvidence, ...],
) -> CandidateVerification:
    return verify_candidate(candidate, evidence)
