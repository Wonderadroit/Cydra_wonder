"""Deterministic reconstruction of persisted causal reasoning chains."""
from __future__ import annotations
from dataclasses import dataclass
from .system_model import SystemModel

@dataclass(frozen=True)
class CausalChainTrace:
    chain_id: str
    hypothesis_id: str
    observation_id: str
    outcome_evidence_id: str
    verification_id: str
    belief_update_id: str
    @property
    def evidence_ids(self) -> tuple[str, str]:
        return self.outcome_evidence_id, self.verification_id

def reconstruct_causal_chain(model: SystemModel, chain_id: str) -> CausalChainTrace:
    chain = model.nodes.get(chain_id)
    if chain is None or chain.kind != "causal_chain":
        raise KeyError(f"causal chain not found: {chain_id}")
    declared_evidence = tuple(chain.attributes.get("evidence_ids", ()))
    def targets(source: str, relation: str) -> list[str]:
        return [e.target for e in model.edges if e.source == source and e.relation == relation and e.attributes.get("causal_chain_id") == chain_id]
    def target(source: str, relation: str) -> str:
        matches = targets(source, relation)
        if len(matches) != 1:
            raise ValueError(f"expected exactly one {relation} link for {chain_id}")
        return matches[0]
    motivating = [e.source for e in model.edges if e.target == chain_id and e.relation == "motivates" and e.attributes.get("causal_chain_id") == chain_id]
    if len(motivating) != 1:
        raise ValueError(f"expected exactly one motivates link for {chain_id}")
    hypothesis_id = motivating[0]
    observation_id = target(chain_id, "plans")
    evidence_id = target(observation_id, "produced_evidence")
    verification_id = target(evidence_id, "informs")
    belief_update_id = target(verification_id, "updates")
    if declared_evidence and set(declared_evidence) != {evidence_id, verification_id}:
        raise ValueError(f"causal evidence references do not match persisted chain: {chain_id}")
    expected = {(hypothesis_id, "motivates", chain_id), (chain_id, "plans", observation_id), (observation_id, "produced_evidence", evidence_id), (evidence_id, "informs", verification_id), (verification_id, "updates", belief_update_id)}
    for source, relation, target_id in expected:
        matches = [e for e in model.edges if e.source == source and e.relation == relation and e.target == target_id and e.attributes.get("causal_chain_id") == chain_id]
        if len(matches) != 1:
            raise ValueError(f"causal-chain link is missing or duplicated: {source} -[{relation}]-> {target_id}")
    return CausalChainTrace(chain_id, hypothesis_id, observation_id, evidence_id, verification_id, belief_update_id)
