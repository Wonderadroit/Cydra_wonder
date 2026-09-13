"""Persistent competing-hypothesis contradictions in the canonical SystemModel."""
from __future__ import annotations
from dataclasses import dataclass
from .graph_semantics import validate_graph
from .system_model import Edge, Node, SystemModel

@dataclass(frozen=True)
class Contradiction:
    contradiction_id: str
    evidence_ids: tuple[str, ...]
    competing_hypothesis_ids: tuple[str, ...]


def persist_contradiction(model: SystemModel, contradiction: Contradiction) -> None:
    if not contradiction.contradiction_id.strip():
        raise ValueError("contradiction ID must not be empty")
    if len(contradiction.competing_hypothesis_ids) < 2:
        raise ValueError("contradiction requires at least two competing hypotheses")
    if len(set(contradiction.competing_hypothesis_ids)) != len(contradiction.competing_hypothesis_ids):
        raise ValueError("contradiction hypotheses must be unique")
    for hypothesis_id in contradiction.competing_hypothesis_ids:
        node = model.nodes.get(hypothesis_id)
        if node is None:
            raise KeyError(f"missing contradiction hypothesis: {hypothesis_id}")
        if node.kind != "hypothesis":
            raise ValueError(f"contradiction endpoint is not a hypothesis: {hypothesis_id}")
    for evidence_id in contradiction.evidence_ids:
        node = model.nodes.get(evidence_id)
        if node is None:
            raise KeyError(f"missing contradiction evidence: {evidence_id}")
        if node.kind != "evidence":
            raise ValueError(f"contradiction evidence is not evidence: {evidence_id}")
    if contradiction.contradiction_id in model.nodes:
        raise ValueError(f"contradiction already exists: {contradiction.contradiction_id}")

    node = Node(contradiction.contradiction_id, "evidence", contradiction.contradiction_id, {
        "contradiction": True,
        "competing_hypothesis_ids": list(contradiction.competing_hypothesis_ids),
        "evidence_ids": list(contradiction.evidence_ids),
    })
    links = []
    hypotheses = contradiction.competing_hypothesis_ids
    for index, left in enumerate(hypotheses):
        for right in hypotheses[index + 1:]:
            links.append(Edge(left, "contradicts", right, {"contradiction_id": contradiction.contradiction_id}))
    for evidence_id in contradiction.evidence_ids:
        links.append(Edge(evidence_id, "informs", contradiction.contradiction_id, {"contradiction_id": contradiction.contradiction_id}))

    prospective = SystemModel()
    prospective.nodes = dict(model.nodes)
    prospective.edges = list(model.edges)
    prospective.nodes[node.node_id] = node
    prospective.edges.extend(links)
    errors = validate_graph(prospective)
    if errors:
        raise ValueError(f"contradiction violates graph semantics: {errors[0]}")
    model.add_node(node)
    for edge in links:
        model.add_edge(edge)
