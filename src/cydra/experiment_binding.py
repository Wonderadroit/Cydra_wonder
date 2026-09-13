"""Fail-closed binding between canonical hypotheses, observations, and generated tests."""
from __future__ import annotations

from dataclasses import dataclass
import re

from .graph_semantics import validate_graph
from .system_model import Node, SystemModel


@dataclass(frozen=True)
class ExperimentBinding:
    hypothesis_id: str
    observation_id: str
    target_function_id: str
    source_marker: str

    def __post_init__(self) -> None:
        for value, name in (
            (self.hypothesis_id, "hypothesis_id"),
            (self.observation_id, "observation_id"),
            (self.target_function_id, "target_function_id"),
            (self.source_marker, "source_marker"),
        ):
            if not value.strip():
                raise ValueError(f"{name} must not be empty")


def _node(model: SystemModel, kind: str, identifier: str) -> Node:
    node_id = f"{kind}:{identifier}"
    node = model.nodes.get(node_id)
    if node is None:
        raise KeyError(f"missing canonical {kind}: {node_id}")
    if node.kind != kind:
        raise ValueError(f"canonical node kind mismatch: {node_id}")
    return node


def bind_experiment(
    model: SystemModel,
    *,
    hypothesis_id: str,
    observation_id: str,
    target_function_id: str,
    generated_source: str,
    source_marker: str | None = None,
) -> ExperimentBinding:
    """Bind one generated experiment to exactly one hypothesis and function.

    The binding is rejected unless the observation already tests the supplied
    hypothesis, the observation targets the supplied invariant, and the
    generated source contains both the hypothesis marker and the exact target
    function name. This prevents a generic PoC from being credited as testing
    a different hypothesis merely because it executed successfully.
    """
    hypothesis = _node(model, "hypothesis", hypothesis_id)
    observation = _node(model, "observation", observation_id)
    target = _node(model, "function", target_function_id)
    if not generated_source.strip():
        raise ValueError("generated_source must not be empty")

    tests = any(
        edge.source == observation.node_id
        and edge.relation == "tests"
        and edge.target == hypothesis.node_id
        for edge in model.edges
    )
    if not tests:
        raise ValueError("observation does not test the supplied hypothesis")

    observed_target = observation.attributes.get("target_function_id")
    if observed_target is not None and observed_target != target.node_id:
        raise ValueError("observation target function conflicts with supplied target")

    marker = source_marker or f"CYDRA-HYPOTHESIS: {hypothesis_id}"
    if marker not in generated_source:
        raise ValueError("generated experiment is missing its canonical hypothesis marker")

    function_name = target.label
    if not re.search(rf"\b{re.escape(function_name)}\s*\(", generated_source):
        raise ValueError(f"generated experiment does not invoke target function: {function_name}")

    binding = ExperimentBinding(hypothesis_id, observation_id, target_function_id, marker)
    attributes = dict(observation.attributes)
    existing = attributes.get("experiment_binding")
    serialized = {
        "hypothesis_id": hypothesis.node_id,
        "observation_id": observation.node_id,
        "target_function_id": target.node_id,
        "source_marker": marker,
    }
    if existing is not None and existing != serialized:
        raise ValueError("observation already has a conflicting experiment binding")
    attributes.update({"target_function_id": target.node_id, "bound_hypothesis_id": hypothesis.node_id, "experiment_binding": serialized, "binding_status": "bound"})

    prospective = SystemModel.from_dict(model.export())
    prospective.nodes[observation.node_id] = Node(observation.node_id, observation.kind, observation.label, attributes)
    errors = validate_graph(prospective)
    if errors:
        raise ValueError("experiment binding violates canonical graph: " + errors[0])
    model.nodes = prospective.nodes
    model.edges = prospective.edges
    return binding


def validate_experiment_binding(model: SystemModel, binding: ExperimentBinding) -> bool:
    """Verify that persisted binding still points to the same graph objects."""
    observation = _node(model, "observation", binding.observation_id)
    hypothesis = _node(model, "hypothesis", binding.hypothesis_id)
    target = _node(model, "function", binding.target_function_id)
    if observation.attributes.get("binding_status") != "bound":
        return False
    persisted = observation.attributes.get("experiment_binding")
    expected = {
        "hypothesis_id": hypothesis.node_id,
        "observation_id": observation.node_id,
        "target_function_id": target.node_id,
        "source_marker": binding.source_marker,
    }
    if persisted != expected:
        return False
    return any(e.source == observation.node_id and e.relation == "tests" and e.target == hypothesis.node_id for e in model.edges)
