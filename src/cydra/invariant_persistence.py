"""Persist invariant candidates and verification state without asserting truth."""
from __future__ import annotations
from .invariants import InvariantCandidate, CandidateVerification
from .system_model import Edge, Node, SystemModel


def persist_invariant_verification(model: SystemModel, candidate: InvariantCandidate, verification: CandidateVerification) -> None:
    existing = model.nodes.get(candidate.candidate_id)
    attributes = {
        "source_ids": list(candidate.source_ids),
        "confidence": candidate.confidence,
        "evidence_count": candidate.evidence_count,
        "provenance": "system_model_candidate",
        "verification_state": verification.state.value,
        "verification_confidence": verification.confidence,
        "verification_evidence_ids": list(verification.evidence_ids),
    }
    if existing is None:
        model.add_node(Node(candidate.candidate_id, "invariant", candidate.statement, attributes))
    elif existing.kind != "invariant":
        raise ValueError(f"invariant ID conflicts with non-invariant node: {candidate.candidate_id}")
    else:
        model.nodes[candidate.candidate_id] = Node(existing.node_id, existing.kind, existing.label, {**existing.attributes, **attributes})
    for evidence_id in verification.supporting_ids:
        if evidence_id in model.nodes:
            model.add_edge(Edge(candidate.candidate_id, "verified_by", evidence_id, {"provenance": "candidate_verification"}))
    for evidence_id in verification.contradicting_ids:
        if evidence_id in model.nodes:
            model.add_edge(Edge(candidate.candidate_id, "contradicted_by", evidence_id, {"provenance": "candidate_verification"}))
