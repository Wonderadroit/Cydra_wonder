"""Record externally produced observation outcomes as auditable evidence."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping
from .graph_semantics import validate_graph
from .system_model import Edge, Node, SystemModel

@dataclass(frozen=True)
class ObservationOutcome:
    observation_id: str
    outcome_id: str
    result: str
    source: str
    confidence: float = 1.0
    hypothesis_id: str | None = None
    target_function_id: str | None = None
    def __post_init__(self) -> None:
        for value, name in ((self.observation_id,"observation_id"),(self.outcome_id,"outcome_id"),(self.result,"result"),(self.source,"source")):
            if not value.strip(): raise ValueError(f"{name} must not be empty")
        if self.hypothesis_id is not None and not self.hypothesis_id.strip(): raise ValueError("hypothesis_id must not be empty")
        if self.target_function_id is not None and not self.target_function_id.strip(): raise ValueError("target_function_id must not be empty")
        if not 0.0 <= self.confidence <= 1.0: raise ValueError("confidence must be between 0 and 1")
    @property
    def evidence_id(self) -> str:
        return f"observation_outcome:{self.outcome_id}"

def record_observation_outcome(model: SystemModel, *, observation_id: str, outcome_id: str, result: str, source: str, confidence: float = 1.0, metadata: Mapping[str, object] | None = None) -> ObservationOutcome:
    node_id=f"observation:{observation_id}"
    planned=model.nodes.get(node_id)
    if planned is None: raise KeyError(f"unknown observation plan: {node_id}")
    if planned.kind != "observation": raise ValueError(f"model node is not an observation: {node_id}")
    if planned.attributes.get("status") != "planned": raise ValueError(f"observation is not awaiting an outcome: {node_id}")
    if not result.strip() or not source.strip() or not outcome_id.strip(): raise ValueError("outcome_id, result, and source must not be empty")
    if not 0.0 <= confidence <= 1.0: raise ValueError("confidence must be between 0 and 1")
    evidence_node_id=f"observation_outcome:{outcome_id}"
    if evidence_node_id in model.nodes: raise ValueError(f"observation outcome already exists: {evidence_node_id}")
    binding = planned.attributes.get("experiment_binding")
    if planned.attributes.get("binding_status") == "bound" and not isinstance(binding, dict):
        raise ValueError("bound observation is missing canonical experiment binding")
    hypothesis_id = binding.get("hypothesis_id") if isinstance(binding, dict) else None
    target_function_id = binding.get("target_function_id") if isinstance(binding, dict) else planned.attributes.get("target_function_id")
    evidence_attributes={"observation_id":observation_id,"result":result,"source":source,"confidence":confidence,"metadata":dict(metadata or {})}
    if isinstance(binding, dict):
        evidence_attributes["experiment_binding"] = dict(binding)
        evidence_attributes["hypothesis_id"] = hypothesis_id
        evidence_attributes["target_function_id"] = target_function_id
    evidence=Node(evidence_node_id,"evidence",result,evidence_attributes)
    edges=[Edge(node_id,"produced",evidence_node_id,{"executed_externally":True})]
    if isinstance(binding, dict):
        if hypothesis_id not in model.nodes:
            raise KeyError(f"bound hypothesis no longer exists: {hypothesis_id}")
        edges.append(Edge(evidence_node_id,"informs",hypothesis_id,{"observation_id":observation_id,"bound_experiment":True}))
    prospective=SystemModel(); prospective.nodes=dict(model.nodes); prospective.edges=list(model.edges)
    prospective.nodes[evidence_node_id]=evidence
    prospective.edges.extend(edges)
    prospective.nodes[node_id]=Node(planned.node_id,planned.kind,planned.label,{**planned.attributes,"status":"completed","executed":True,"outcome_id":outcome_id})
    errors=validate_graph(prospective)
    if errors: raise ValueError(f"observation outcome violates canonical graph: {errors[0]}")
    model.add_node(evidence)
    for edge in edges: model.add_edge(edge)
    model.update_node_attributes(node_id,{"status":"completed","executed":True,"outcome_id":outcome_id})
    return ObservationOutcome(observation_id,outcome_id,result,source,confidence,hypothesis_id,target_function_id)
