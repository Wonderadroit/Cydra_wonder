"""Persist hypothesis belief transitions as canonical, auditable graph evidence."""
from __future__ import annotations
from .hypotheses import BeliefUpdate, Hypothesis
from .system_model import Edge, Node, SystemModel


def persist_belief_update(model: SystemModel, hypothesis: Hypothesis, update: BeliefUpdate, *, update_id: str) -> None:
    if update.hypothesis_id != hypothesis.hypothesis_id:
        raise ValueError("belief update hypothesis does not match hypothesis")
    if update_id in model.nodes:
        raise ValueError(f"belief update already exists: {update_id}")
    if hypothesis.hypothesis_id not in model.nodes:
        raise KeyError(f"missing hypothesis node: {hypothesis.hypothesis_id}")
    if any(e.target == update_id for e in model.edges):
        raise ValueError(f"belief update target already referenced: {update_id}")
    model.add_node(Node(update_id, "belief", update_id, {
        "hypothesis_id": update.hypothesis_id,
        "prior_belief": update.prior_belief,
        "posterior_belief": update.posterior_belief,
        "prior_state": update.prior_state.value,
        "posterior_state": update.posterior_state.value,
        "evidence_ids": list(update.evidence_ids),
        "rationale": update.rationale,
        "persisted": True,
    }))
    model.add_edge(Edge(hypothesis.hypothesis_id, "updated_to", update_id, {"provenance": "belief_update"}))
    for evidence_id in update.evidence_ids:
        if evidence_id in model.nodes:
            model.add_edge(Edge(evidence_id, "updates", update_id, {"provenance": "belief_update"}))
