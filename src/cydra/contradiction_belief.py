"""Conservative belief updates driven by contradiction re-evaluation."""
from __future__ import annotations
from dataclasses import dataclass
from .contradiction_re_evaluation import ContradictionDisposition
from .system_model import Edge, Node, SystemModel

@dataclass(frozen=True)
class ContradictionBeliefUpdate:
    belief_id: str
    contradiction_id: str
    prior_confidence: float
    posterior_confidence: float
    disposition: ContradictionDisposition
    evidence_id: str
    rationale: str


def update_contradiction_belief(belief_id: str, contradiction_id: str, prior_confidence: float, disposition: ContradictionDisposition, evidence_id: str, step: float = 0.25) -> ContradictionBeliefUpdate:
    if not belief_id.strip() or not contradiction_id.strip() or not evidence_id.strip():
        raise ValueError("belief_id, contradiction_id and evidence_id must not be empty")
    if not 0.0 <= prior_confidence <= 1.0:
        raise ValueError("prior_confidence must be between 0 and 1")
    if not 0.0 < step <= 1.0:
        raise ValueError("step must be greater than 0 and at most 1")
    if disposition is ContradictionDisposition.SUPPORTED:
        posterior = prior_confidence + step * (1.0 - prior_confidence)
    elif disposition is ContradictionDisposition.REJECTED:
        posterior = prior_confidence * (1.0 - step)
    else:
        posterior = prior_confidence
    return ContradictionBeliefUpdate(belief_id, contradiction_id, prior_confidence, posterior, disposition, evidence_id, "belief updated from recorded re-evaluation; uncertainty preserved for inconclusive evidence")


def persist_contradiction_belief_update(model: SystemModel, update: ContradictionBeliefUpdate, update_id: str) -> None:
    if not update_id.strip():
        raise ValueError("update_id must not be empty")
    if update.contradiction_id not in model.nodes or model.nodes[update.contradiction_id].attributes.get("contradiction") is not True:
        raise KeyError(f"missing contradiction node: {update.contradiction_id}")
    if update.evidence_id not in model.nodes or model.nodes[update.evidence_id].kind != "evidence":
        raise KeyError(f"missing evidence node: {update.evidence_id}")
    if update_id in model.nodes:
        raise ValueError(f"belief update already exists: {update_id}")
    node = Node(update_id, "evidence", update_id, {"belief_update": True, "belief_id": update.belief_id, "contradiction_id": update.contradiction_id, "prior_confidence": update.prior_confidence, "posterior_confidence": update.posterior_confidence, "disposition": update.disposition.value, "rationale": update.rationale})
    model.add_node(node)
    model.add_edge(Edge(update.contradiction_id, "updated_by", update_id))
    model.add_edge(Edge(update_id, "based_on", update.evidence_id))


def apply_current_belief(model: SystemModel, update: ContradictionBeliefUpdate, update_id: str):
    if update_id not in model.nodes:
        raise KeyError(f"missing persisted belief update: {update_id}")
    if update.belief_id in model.nodes and model.nodes[update.belief_id].kind != "belief":
        raise ValueError(f"belief id is not a belief node: {update.belief_id}")
    if update.belief_id not in model.nodes:
        model.add_node(Node(update.belief_id, "belief", update.belief_id, {"current_confidence": update.posterior_confidence, "current_source_update": update_id}))
    else:
        old = model.nodes[update.belief_id]
        attrs = dict(old.attributes)
        attrs.update(current_confidence=update.posterior_confidence, current_source_update=update_id)
        model.nodes[update.belief_id] = Node(old.node_id, old.kind, old.label, attrs)
    model.add_edge(Edge(update_id, "updates", update.belief_id))
    return update.posterior_confidence
