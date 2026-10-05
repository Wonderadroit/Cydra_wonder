from __future__ import annotations
import hashlib
from typing import Sequence
from .execution_adapter import AdapterObservation, AdapterStatus
from .invariants import VerificationEvidence, VerificationRole
from .hypotheses import Hypothesis

def authorization_differential_evidence(hypothesis: Hypothesis, observations: Sequence[AdapterObservation]) -> tuple[VerificationEvidence,...]:
    if len(observations)<2:
        return (VerificationEvidence(f"{hypothesis.hypothesis_id}:insufficient-observation",VerificationRole.NEUTRAL,1.0,"authorization comparison requires both owner and comparison observations"),)
    owner, comparison = observations[:2]
    if owner.status != AdapterStatus.EXECUTED or comparison.status != AdapterStatus.EXECUTED:
        return (VerificationEvidence(f"{hypothesis.hypothesis_id}:capability-gap",VerificationRole.NEUTRAL,1.0,"adapter capability/transport failure is not security evidence"),)
    ov=owner.value if isinstance(owner.value,dict) else {}; cv=comparison.value if isinstance(comparison.value,dict) else {}
    os,cs,ob,cb=ov.get("status_code"),cv.get("status_code"),ov.get("body_sha256"),cv.get("body_sha256")
    if os is None or cs is None:
        return (VerificationEvidence(f"{hypothesis.hypothesis_id}:missing-authorization-observation",VerificationRole.NEUTRAL,1.0,"responses did not contain status information required for comparison"),)
    if os != cs:
        digest=hashlib.sha256(f"{os}:{cs}:{ob}:{cb}".encode()).hexdigest()[:16]
        return (VerificationEvidence(f"{hypothesis.hypothesis_id}:authorization-divergence:{digest}",VerificationRole.SUPPORTS,0.8,"owner and comparison identities produced different HTTP authorization outcomes for the same modeled resource"),)
    if ob and cb and ob==cb:
        return (VerificationEvidence(f"{hypothesis.hypothesis_id}:identical-response",VerificationRole.CONTRADICTS,0.85,"owner and comparison identities produced the same status and response body for the same modeled resource"),)
    return (VerificationEvidence(f"{hypothesis.hypothesis_id}:same-status-different-body",VerificationRole.NEUTRAL,0.7,"owner and comparison identities shared a status code but differed in body; authorization semantics require further causal investigation"),)
