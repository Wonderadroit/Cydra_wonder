"""Evidence-backed causal verification over the canonical reasoning graph."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from .causal_reconstruction import CausalChainTrace, reconstruct_causal_chain
from .system_model import SystemModel

class CausalVerificationState(str, Enum):
    VERIFIED = "verified"
    REJECTED = "rejected"
    UNRESOLVED = "unresolved"

@dataclass(frozen=True)
class CausalVerificationResult:
    state: CausalVerificationState
    chain_id: str
    trace: CausalChainTrace | None
    evidence_ids: tuple[str, ...]
    reasons: tuple[str, ...]

def verify_persisted_causal_chain(model: SystemModel, chain_id: str) -> CausalVerificationResult:
    try:
        trace = reconstruct_causal_chain(model, chain_id)
    except (KeyError, ValueError) as exc:
        return CausalVerificationResult(CausalVerificationState.REJECTED, chain_id, None, (), (str(exc),))
    evidence_ids = tuple(trace.evidence_ids)
    missing = [eid for eid in evidence_ids if eid not in model.nodes or model.nodes[eid].kind != "evidence"]
    if missing:
        return CausalVerificationResult(CausalVerificationState.REJECTED, chain_id, trace, evidence_ids, (f"causal evidence is missing: {', '.join(missing)}",))
    supporting = [e for e in model.edges if e.source in evidence_ids and e.target == trace.hypothesis_id and e.relation == "supports"]
    if not supporting:
        return CausalVerificationResult(CausalVerificationState.UNRESOLVED, chain_id, trace, evidence_ids, ("causal evidence does not explicitly support the chain hypothesis",))
    belief = model.nodes.get(trace.belief_update_id)
    if belief is None or belief.kind != "belief":
        return CausalVerificationResult(CausalVerificationState.REJECTED, chain_id, trace, evidence_ids, ("causal chain belief-transition anchor is missing",))
    declared = belief.attributes.get("hypothesis_id")
    if declared is not None and declared != trace.hypothesis_id:
        return CausalVerificationResult(CausalVerificationState.REJECTED, chain_id, trace, evidence_ids, ("belief-transition hypothesis does not match causal-chain hypothesis",))
    return CausalVerificationResult(CausalVerificationState.VERIFIED, chain_id, trace, evidence_ids, ())
