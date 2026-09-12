"""Persist information-gain resolution plans without executing them."""
from __future__ import annotations
from dataclasses import dataclass
from .contradiction_model import Contradiction
from .graph_semantics import validate_graph
from .system_model import Edge, Node, SystemModel
from .test_planning import ObservationOption

@dataclass(frozen=True)
class ResolutionPlan:
    contradiction_id: str
    observation_id: str
    utility: float
    rationale: str


def plan_contradiction_resolution(contradiction: Contradiction, observations: tuple[ObservationOption, ...]) -> tuple[ResolutionPlan, ...]:
    if not contradiction.contradiction_id.strip():
        raise ValueError("contradiction_id must not be empty")
    if len(contradiction.competing_hypothesis_ids) < 2:
        raise ValueError("contradiction requires competing hypotheses")
    target_count = len(contradiction.competing_hypothesis_ids)
    plans = []
    for option in observations:
        states = len(set(option.expected_states))
        utility = 0.0 if states < 2 else min(1.0, (states - 1) / target_count) / option.cost
        plans.append(ResolutionPlan(contradiction.contradiction_id, option.observation_id, utility, "prioritizes distinguishable outcomes per unit cost; no execution or resolution performed"))
    return tuple(sorted(plans, key=lambda p: (-p.utility, p.observation_id)))


def persist_resolution_plan(model: SystemModel, plan: ResolutionPlan, record_id: str) -> None:
    if not record_id.strip():
        raise ValueError("record_id must not be empty")
    contradiction = model.nodes.get(plan.contradiction_id)
    observation = model.nodes.get(plan.observation_id)
    if contradiction is None or contradiction.attributes.get("contradiction") is not True:
        raise KeyError(f"missing contradiction node: {plan.contradiction_id}")
    if observation is None or observation.kind != "observation":
        raise KeyError(f"missing observation node: {plan.observation_id}")
    if record_id in model.nodes:
        raise ValueError(f"resolution record already exists: {record_id}")
    node = Node(record_id, "evidence", record_id, {"resolution_plan": True, "contradiction_id": plan.contradiction_id, "utility": plan.utility, "rationale": plan.rationale, "executed": False})
    links = (Edge(plan.contradiction_id, "has_resolution_plan", record_id), Edge(record_id, "selects_observation", plan.observation_id))
    prospective = SystemModel()
    prospective.nodes = dict(model.nodes)
    prospective.edges = list(model.edges)
    prospective.nodes[node.node_id] = node
    prospective.edges.extend(links)
    errors = validate_graph(prospective)
    if errors:
        raise ValueError(f"resolution plan violates graph semantics: {errors[0]}")
    model.add_node(node)
    for edge in links:
        model.add_edge(edge)
