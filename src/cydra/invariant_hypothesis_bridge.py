"""Translate explicitly supported invariant candidates into testable hypotheses."""
from __future__ import annotations
from dataclasses import dataclass
from .hypotheses import Hypothesis
from .invariants import InvariantCandidate, VerificationState
from .system_model import Edge, Node, SystemModel

@dataclass(frozen=True)
class InvariantHypothesis:
    hypothesis_id: str
    invariant_id: str
    statement: str
    confidence: float


def hypotheses_from_verified_invariants(model: SystemModel, candidates: tuple[InvariantCandidate, ...]) -> tuple[InvariantHypothesis, ...]:
    results = []
    for candidate in candidates:
        node = model.nodes.get(candidate.candidate_id)
        if node is None or node.kind != "invariant":
            continue
        if node.attributes.get("verification_state") != VerificationState.SUPPORTED.value:
            continue
        results.append(InvariantHypothesis(
            hypothesis_id=f"hypothesis:{candidate.candidate_id}",
            invariant_id=candidate.candidate_id,
            statement=f"Violation of invariant: {candidate.statement}",
            confidence=float(node.attributes.get("verification_confidence", candidate.confidence)),
        ))
    return tuple(results)


def persist_invariant_hypotheses(model: SystemModel, hypotheses: tuple[InvariantHypothesis, ...]) -> None:
    for hypothesis in hypotheses:
        invariant = model.nodes.get(hypothesis.invariant_id)
        if invariant is None or invariant.kind != "invariant":
            raise KeyError(f"invariant node missing: {hypothesis.invariant_id}")
        existing = model.nodes.get(hypothesis.hypothesis_id)
        if existing is None:
            model.add_node(Node(hypothesis.hypothesis_id, "hypothesis", hypothesis.statement, {
                "invariant_id": hypothesis.invariant_id,
                "confidence": hypothesis.confidence,
                "provenance": "verified_invariant",
            }))
        elif existing.kind != "hypothesis":
            raise ValueError(f"hypothesis ID conflicts with non-hypothesis node: {hypothesis.hypothesis_id}")
        model.add_edge(Edge(hypothesis.invariant_id, "informs", hypothesis.hypothesis_id, {
            "provenance": "verified_invariant", "rationale": "supported invariant bridge",
        }))
