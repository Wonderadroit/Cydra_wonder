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

    outcome_evidence = model.nodes[trace.outcome_evidence_id]
    binding = outcome_evidence.attributes.get("experiment_binding")
    if isinstance(binding, dict):
        if binding.get("hypothesis_id") != trace.hypothesis_id:
            return CausalVerificationResult(CausalVerificationState.REJECTED, chain_id, trace, evidence_ids, ("experiment-bound outcome evidence points to a different hypothesis",))
        bound_observation = binding.get("observation_id")
        if bound_observation != trace.observation_id:
            return CausalVerificationResult(CausalVerificationState.REJECTED, chain_id, trace, evidence_ids, ("experiment-bound outcome evidence points to a different observation",))
        observation = model.nodes.get(trace.observation_id)
        if observation is None or observation.kind != "observation":
            return CausalVerificationResult(CausalVerificationState.REJECTED, chain_id, trace, evidence_ids, ("causal observation anchor is missing",))
        bound_target = binding.get("target_function_id")
        observed_target = observation.attributes.get("target_function_id")
        if bound_target is not None and observed_target is not None and bound_target != observed_target:
            return CausalVerificationResult(CausalVerificationState.REJECTED, chain_id, trace, evidence_ids, ("experiment-bound target function conflicts with observation target",))

    supporting = [e for e in model.edges if e.source in evidence_ids and e.target == trace.hypothesis_id and e.relation == "supports"]
    contradicting = [e for e in model.edges if e.source in evidence_ids and e.target == trace.hypothesis_id and e.relation == "contradicts"]
    if not supporting and not contradicting:
        return CausalVerificationResult(CausalVerificationState.UNRESOLVED, chain_id, trace, evidence_ids, ("causal evidence does not explicitly support or contradict the chain hypothesis",))
    belief = model.nodes.get(trace.belief_update_id)
    if belief is None or belief.kind != "belief":
        return CausalVerificationResult(CausalVerificationState.REJECTED, chain_id, trace, evidence_ids, ("causal chain belief-transition anchor is missing",))
    declared = belief.attributes.get("hypothesis_id")
    if declared is not None and declared != trace.hypothesis_id:
        return CausalVerificationResult(CausalVerificationState.REJECTED, chain_id, trace, evidence_ids, ("belief-transition hypothesis does not match causal-chain hypothesis",))
    return CausalVerificationResult(CausalVerificationState.VERIFIED, chain_id, trace, evidence_ids, ())
