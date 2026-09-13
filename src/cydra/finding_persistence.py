"""Persist a finding only after the canonical causal gate is READY."""
from __future__ import annotations
from .finding import Finding
from .finding_gate import FindingCandidate, GateDecision, evaluate_finding_graph
from .system_model import Edge, Node, SystemModel


def persist_finding(model: SystemModel, *, candidate: FindingCandidate, finding: Finding) -> None:
    if finding.finding_id in model.nodes:
        raise ValueError(f"finding already exists: {finding.finding_id}")
    if not finding.causal_chain_id:
        raise ValueError("finding requires a causal-chain reference")
    decision = evaluate_finding_graph(
        model,
        candidate=candidate,
        finding_id=finding.finding_id,
        hypothesis_id=finding.hypothesis_id,
        evidence_ids=finding.evidence_ids,
        causal_chain_id=finding.causal_chain_id,
    )
    if decision.decision is not GateDecision.READY:
        raise ValueError(f"finding is not ready for persistence: {decision.decision.value}: {decision.reasons[0] if decision.reasons else 'unspecified'}")
    node = Node(finding.finding_id, "finding", finding.title, {
        "persisted": True,
        "finding_id": finding.finding_id,
        "title": finding.title,
        "summary": finding.summary,
        "severity": finding.severity,
        "impact": {"level": finding.impact.level.value, "asset_at_risk": finding.impact.asset_at_risk, "consequence": finding.impact.consequence, "prerequisites": list(finding.impact.prerequisites)},
        "affected_components": list(finding.affected_components),
        "evidence_ids": list(finding.evidence_ids),
        "hypothesis_id": finding.hypothesis_id,
        "poc_reference": finding.poc_reference,
        "causal_chain_id": finding.causal_chain_id,
        "audit_session_id": finding.audit_session_id,
    })
    edges = [Edge(finding.finding_id, "about", finding.hypothesis_id, {"provenance": "finding_gate"}),
             Edge(finding.finding_id, "traced_by", finding.causal_chain_id, {"provenance": "causal_verification"})]
    edges.extend(Edge(finding.finding_id, "supported_by", evidence_id, {"provenance": "finding_gate"}) for evidence_id in finding.evidence_ids)
    prospective = SystemModel()
    prospective.nodes = dict(model.nodes)
    prospective.edges = list(model.edges)
    prospective.nodes[node.node_id] = node
    prospective.edges.extend(edges)
    errors = prospective.validate()
    if errors:
        raise ValueError(f"finding violates canonical model: {errors[0]}")
    model.add_node(node)
    for edge in edges:
        model.add_edge(edge)
