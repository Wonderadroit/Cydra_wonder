"""Persist hypothesis belief transitions as canonical, auditable graph evidence."""
from __future__ import annotations
from .belief_persistence import BeliefUpdate, Hypothesis
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
    evidence_ids = tuple(update.evidence_ids)
    missing = tuple(eid for eid in evidence_ids if eid not in model.nodes or model.nodes[eid].kind != "evidence")
    if missing:
        raise ValueError(f"belief update references missing evidence: {', '.join(missing)}")

    prospective = SystemModel.from_dict(model.export())
    prospective.add_node(Node(update_id, "belief", update_id, {
        "hypothesis_id": update.hypothesis_id,
        "prior_belief": update.prior_belief,
        "posterior_belief": update.posterior_belief,
        "prior_state": update.prior_state.value,
        "posterior_state": update.posterior_state.value,
        "evidence_ids": list(evidence_ids),
        "rationale": update.rationale,
        "persisted": True,
    }))
    prospective.add_edge(Edge(hypothesis.hypothesis_id, "updated_to", update_id, {"provenance": "belief_update"}))
    for evidence_id in evidence_ids:
        prospective.add_edge(Edge(evidence_id, "updates", update_id, {"provenance": "belief_update"}))
    prospective.update_node_attributes(hypothesis.hypothesis_id, {
        "belief": update.posterior_belief,
        "state": update.posterior_state.value,
        "last_belief_update": update_id,
    })
    from .graph_semantics import validate_graph
    errors = validate_graph(prospective)
    if errors:
        raise ValueError(f"belief update violates graph semantics: {errors[0]}")

    model.nodes = prospective.nodes
    model.edges = prospective.edges
