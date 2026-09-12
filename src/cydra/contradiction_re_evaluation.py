"""Conservative re-evaluation of contradictions from recorded evidence."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum

class ContradictionDisposition(str, Enum):
    UNRESOLVED = "unresolved"
    SUPPORTED = "supported"
    REJECTED = "rejected"
    INCONCLUSIVE = "inconclusive"

@dataclass(frozen=True)
class ReEvaluation:
    contradiction_id: str
    disposition: ContradictionDisposition
    evidence_id: str
    rationale: str

def reevaluate_contradiction(contradiction_id: str, evidence_id: str, *, supports_hypothesis: bool | None) -> ReEvaluation:
    if not contradiction_id.strip() or not evidence_id.strip():
        raise ValueError("contradiction_id and evidence_id must not be empty")
    if supports_hypothesis is True:
        return ReEvaluation(contradiction_id, ContradictionDisposition.SUPPORTED, evidence_id, "external evidence supports the selected hypothesis")
    if supports_hypothesis is False:
        return ReEvaluation(contradiction_id, ContradictionDisposition.REJECTED, evidence_id, "external evidence rejects the selected hypothesis")
    return ReEvaluation(contradiction_id, ContradictionDisposition.INCONCLUSIVE, evidence_id, "external evidence does not distinguish the competing hypotheses")
