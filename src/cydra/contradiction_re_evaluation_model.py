"""Persist contradiction re-evaluation outcomes without mutating prior evidence."""
from __future__ import annotations
from .contradiction_re_evaluation import ReEvaluation
from .graph_semantics import validate_graph
from .system_model import Edge, Node, SystemModel


def persist_re_evaluation(model: SystemModel, result: ReEvaluation, record_id: str) -> None:
    if not record_id.strip():
        raise ValueError("record_id must not be empty")
    contradiction = model.nodes.get(result.contradiction_id)
    evidence = model.nodes.get(result.evidence_id)
    if contradiction is None or contradiction.attributes.get("contradiction") is not True:
        raise KeyError(f"missing contradiction node: {result.contradiction_id}")
    if evidence is None or evidence.kind != "evidence":
        raise KeyError(f"missing evidence node: {result.evidence_id}")
    if record_id in model.nodes:
        raise ValueError(f"re-evaluation already exists: {record_id}")
    node = Node(record_id, "evidence", record_id, {
        "re_evaluation": True,
        "contradiction_id": result.contradiction_id,
        "disposition": result.disposition.value,
        "rationale": result.rationale,
        "source_evidence_id": result.evidence_id,
    })
    links = (Edge(result.contradiction_id, "re_evaluated_by", record_id), Edge(record_id, "based_on", result.evidence_id))
    prospective = SystemModel()
    prospective.nodes = dict(model.nodes)
    prospective.edges = list(model.edges)
    prospective.nodes[node.node_id] = node
    prospective.edges.extend(links)
    errors = validate_graph(prospective)
    if errors:
        raise ValueError(f"re-evaluation violates graph semantics: {errors[0]}")
    model.add_node(node)
    for edge in links:
        model.add_edge(edge)
