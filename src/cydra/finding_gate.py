"""Conservative finding-promotion gate over the canonical SystemModel."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from .causal_verification import CausalVerificationState, verify_persisted_causal_chain
from .system_model import SystemModel

class GateDecision(str, Enum):
    READY = "READY"
    BLOCKED = "BLOCKED"
    UNRESOLVED = "UNRESOLVED"

@dataclass(frozen=True)
class FindingCandidate:
    in_scope: bool
    known_issue: bool
    evidence: bool
    reproducible: bool
    causal_verified: bool
    impact_assessed: bool
    hypothesis_resolved: bool = True

@dataclass(frozen=True)
class GateResult:
    decision: GateDecision
    reasons: tuple[str, ...]

def evaluate_finding(candidate: FindingCandidate) -> GateResult:
    if not candidate.in_scope:
        return GateResult(GateDecision.BLOCKED, ("target is out of scope",))
    if candidate.known_issue:
        return GateResult(GateDecision.BLOCKED, ("candidate matches a known issue",))
    if not candidate.hypothesis_resolved:
        return GateResult(GateDecision.UNRESOLVED, ("hypothesis remains unresolved",))
    missing = []
    if not candidate.evidence: missing.append("evidence")
    if not candidate.reproducible: missing.append("reproducibility")
    if not candidate.causal_verified: missing.append("causal verification")
    if not candidate.impact_assessed: missing.append("impact assessment")
    if missing: return GateResult(GateDecision.BLOCKED, tuple(missing))
    return GateResult(GateDecision.READY, ())

def evaluate_finding_graph(model: SystemModel, *, candidate: FindingCandidate, finding_id: str, hypothesis_id: str, evidence_ids: tuple[str, ...], causal_chain_id: str) -> GateResult:
    base = evaluate_finding(candidate)
    if base.decision != GateDecision.READY: return base
    if not finding_id.strip() or not hypothesis_id.strip() or not causal_chain_id.strip():
        return GateResult(GateDecision.BLOCKED, ("finding identity or causal-chain reference is missing",))
    hypothesis = model.nodes.get(hypothesis_id)
    if hypothesis is None or hypothesis.kind != "hypothesis":
        return GateResult(GateDecision.BLOCKED, ("finding hypothesis is not canonical",))
    graph_state = str(hypothesis.attributes.get("state", "unresolved"))
    if graph_state == "unresolved" or graph_state == "supported":
        return GateResult(GateDecision.UNRESOLVED, ("canonical hypothesis is not causally established",))
    if graph_state != "causally_established":
        return GateResult(GateDecision.BLOCKED, (f"canonical hypothesis state is {graph_state}; finding requires causal establishment",))
    if not evidence_ids:
        return GateResult(GateDecision.BLOCKED, ("finding has no canonical evidence IDs",))
    missing = tuple(e for e in evidence_ids if e not in model.nodes or model.nodes[e].kind != "evidence")
    if missing:
        return GateResult(GateDecision.BLOCKED, (f"missing canonical evidence: {', '.join(missing)}",))
    supported = any(edge.source in evidence_ids and edge.relation == "supports" and edge.target == hypothesis_id for edge in model.edges)
    if not supported:
        return GateResult(GateDecision.BLOCKED, ("finding evidence does not explicitly support the finding hypothesis",))
    verification = verify_persisted_causal_chain(model, causal_chain_id)
    if verification.state is CausalVerificationState.REJECTED:
        return GateResult(GateDecision.BLOCKED, (f"causal verification rejected: {verification.reasons[0] if verification.reasons else 'invalid chain'}",))
    if verification.state is CausalVerificationState.UNRESOLVED:
        return GateResult(GateDecision.UNRESOLVED, (f"causal verification unresolved: {verification.reasons[0] if verification.reasons else 'insufficient evidence'}",))
    if verification.trace is None or verification.trace.hypothesis_id != hypothesis_id:
        return GateResult(GateDecision.BLOCKED, ("causal chain hypothesis does not match finding hypothesis",))
    if not set(evidence_ids).intersection(verification.evidence_ids):
        return GateResult(GateDecision.BLOCKED, ("finding evidence is disconnected from causal trace",))
    return GateResult(GateDecision.READY, ())
