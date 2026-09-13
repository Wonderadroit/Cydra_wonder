"""Invariant representation, candidate extraction, and evidence-bound verification."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, TYPE_CHECKING
if TYPE_CHECKING:
    from .system_model import SystemModel
class InvariantStatus(str, Enum):
    ASSERTED = "asserted"
    INFERRED = "inferred"
    UNKNOWN = "unknown"
    CONTRADICTED = "contradicted"
class VerificationState(str, Enum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    UNRESOLVED = "unresolved"
class VerificationRole(str, Enum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    NEUTRAL = "neutral"
@dataclass(frozen=True)
class Invariant:
    invariant_id: str
    statement: str
    status: InvariantStatus = InvariantStatus.UNKNOWN
    source_ids: tuple[str, ...] = ()
    confidence: float = 0.0
    metadata: dict[str, str] = field(default_factory=dict)
    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0: raise ValueError("confidence must be between 0 and 1")
        if not self.statement.strip(): raise ValueError("statement must not be empty")
@dataclass(frozen=True)
class InvariantCandidate:
    candidate_id: str
    statement: str
    source_ids: tuple[str, ...]
    confidence: float
    evidence_count: int
    def __post_init__(self) -> None:
        if not self.statement.strip(): raise ValueError("statement must not be empty")
        if not self.source_ids: raise ValueError("candidate requires at least one source")
        if not 0.0 <= self.confidence <= 1.0: raise ValueError("confidence must be between 0 and 1")
        if self.evidence_count < 1: raise ValueError("evidence_count must be positive")
@dataclass(frozen=True)
class VerificationEvidence:
    evidence_id: str
    role: VerificationRole
    confidence: float = 1.0
    rationale: str = ""
    def __post_init__(self) -> None:
        if not self.evidence_id.strip(): raise ValueError("evidence_id must not be empty")
        if not 0.0 <= self.confidence <= 1.0: raise ValueError("confidence must be between 0 and 1")
@dataclass(frozen=True)
class CandidateVerification:
    candidate_id: str
    state: VerificationState
    evidence_ids: tuple[str, ...]
    supporting_ids: tuple[str, ...]
    contradicting_ids: tuple[str, ...]
    confidence: float
    def __post_init__(self) -> None:
        evidence_ids = set(self.evidence_ids)
        if not self.candidate_id.strip(): raise ValueError("candidate_id must not be empty")
        if not set(self.supporting_ids).issubset(evidence_ids): raise ValueError("supporting evidence IDs must be part of evidence_ids")
        if not set(self.contradicting_ids).issubset(evidence_ids): raise ValueError("contradicting evidence IDs must be part of evidence_ids")
        if not 0.0 <= self.confidence <= 1.0: raise ValueError("confidence must be between 0 and 1")
        if self.state == VerificationState.SUPPORTED and not self.supporting_ids: raise ValueError("supported verification requires supporting evidence")
        if self.state == VerificationState.CONTRADICTED and not self.contradicting_ids: raise ValueError("contradicted verification requires contradicting evidence")
        if self.state == VerificationState.UNRESOLVED and (self.supporting_ids or self.contradicting_ids): raise ValueError("unresolved verification cannot contain supporting or contradicting evidence")
@dataclass
class InvariantRegistry:
    invariants: dict[str, Invariant] = field(default_factory=dict)
    def add(self, invariant: Invariant) -> None:
        if invariant.invariant_id in self.invariants: raise ValueError(f"duplicate invariant: {invariant.invariant_id}")
        self.invariants[invariant.invariant_id] = invariant
    def get(self, invariant_id: str) -> Invariant | None: return self.invariants.get(invariant_id)
    def by_status(self, status: InvariantStatus) -> list[Invariant]: return [i for i in self.invariants.values() if i.status == status]
def candidates_from_system_model(model: SystemModel) -> tuple[InvariantCandidate, ...]:
    candidates = []
    for edge in sorted(model.edges, key=lambda e: (e.source, e.relation, e.target)):
        if not edge.attributes.get("evidence_backed") or not edge.attributes.get("candidate"): continue
        provenance = str(edge.attributes.get("provenance", ""))
        if not provenance: continue
        confidence = float(edge.attributes.get("confidence", 0.0))
        source_id = f"{provenance}:{edge.attributes.get('ast_node_id', 'unknown')}"
        candidate_id = f"candidate:{edge.source}:{edge.relation}:{edge.target}"
        statement = f"{edge.source} {edge.relation} {edge.target}"
        candidates.append(InvariantCandidate(candidate_id, statement, (source_id,), confidence, 1))
    return tuple(candidates)
def verify_candidate(candidate: InvariantCandidate, evidence: Iterable[VerificationEvidence]) -> CandidateVerification:
    items = tuple(evidence)
    supporting = tuple(e.evidence_id for e in items if e.role == VerificationRole.SUPPORTS)
    contradicting = tuple(e.evidence_id for e in items if e.role == VerificationRole.CONTRADICTS)
    state = VerificationState.CONTRADICTED if contradicting else VerificationState.SUPPORTED if supporting else VerificationState.UNRESOLVED
    relevant = [e.confidence for e in items if e.role != VerificationRole.NEUTRAL]
    return CandidateVerification(candidate.candidate_id, state, tuple(e.evidence_id for e in items), supporting, contradicting, max(relevant) if relevant else 0.0)
def infer_invariants_from_metadata(records: Iterable[dict[str, str]]) -> InvariantRegistry:
    registry = InvariantRegistry()
    for record in records:
        statement = record.get("statement", "").strip(); invariant_id = record.get("invariant_id", "").strip(); source_id = record.get("source_id", "").strip()
        if not statement or not invariant_id: continue
        registry.add(Invariant(invariant_id, statement, InvariantStatus.INFERRED, (source_id,) if source_id else (), float(record.get("confidence", "0.5"))))
    return registry
