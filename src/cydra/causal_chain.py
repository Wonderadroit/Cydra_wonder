"""Auditable causal-chain persistence for CYDRA reasoning cycles."""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Tuple
from .system_model import Edge, Node, SystemModel
from .graph_semantics import validate_graph

@dataclass(frozen=True)
class CausalChain:
    chain_id: str
    hypothesis_id: str
    observation_id: str
    outcome_evidence_id: str
    verification_id: str
    belief_update_id: str
    @property
    def evidence_ids(self) -> List[str]:
        return [self.outcome_evidence_id, self.verification_id]

def _require_kind(model: SystemModel, node_id: str, kind: str | Tuple[str, ...]) -> None:
    node = model.nodes.get(node_id)
    if node is None:
        raise KeyError(f"missing causal-chain node: {node_id}")
    allowed = (kind,) if isinstance(kind, str) else kind
    if node.kind not in allowed:
        raise ValueError(f"causal-chain node {node_id} has unsupported kind '{node.kind}'")

def persist_causal_chain(model: SystemModel, chain: CausalChain) -> None:
    if not chain.chain_id.strip():
        raise ValueError("causal chain ID must not be empty")
    _require_kind(model, chain.hypothesis_id, "hypothesis")
    _require_kind(model, chain.observation_id, "observation")
    _require_kind(model, chain.outcome_evidence_id, "evidence")
    _require_kind(model, chain.verification_id, ("evidence", "invariant"))
    _require_kind(model, chain.belief_update_id, "belief")
    if chain.chain_id in model.nodes:
        raise ValueError(f"causal chain already exists: {chain.chain_id}")
    links = (
        (chain.hypothesis_id, "motivates", chain.chain_id),
        (chain.chain_id, "plans", chain.observation_id),
        (chain.observation_id, "produced_evidence", chain.outcome_evidence_id),
        (chain.outcome_evidence_id, "informs", chain.verification_id),
        (chain.verification_id, "updates", chain.belief_update_id),
    )
    evidence_ids = list(chain.evidence_ids)
    prospective = SystemModel()
    prospective.nodes = dict(model.nodes)
    prospective.edges = list(model.edges)
    prospective.nodes[chain.chain_id] = Node(chain.chain_id, "causal_chain", chain.chain_id, {"auditable": True, "evidence_ids": evidence_ids})
    prospective.edges.extend(Edge(source, relation, target, {"causal_chain_id": chain.chain_id, "evidence_ids": evidence_ids}) for source, relation, target in links)
    errors = validate_graph(prospective)
    if errors:
        raise ValueError(f"causal chain violates graph semantics: {errors[0]}")
    model.add_node(prospective.nodes[chain.chain_id])
    for source, relation, target in links:
        model.add_edge(Edge(source, relation, target, {"causal_chain_id": chain.chain_id, "evidence_ids": evidence_ids}))
