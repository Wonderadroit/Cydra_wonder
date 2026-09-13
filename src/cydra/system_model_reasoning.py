"""Derive security-relevant reasoning from the canonical SystemModel."""
from __future__ import annotations

from dataclasses import dataclass

from .hypotheses import Hypothesis, HypothesisState
from .information_gain import rank_next_observations
from .invariants import Invariant, InvariantStatus
from .system_model import Edge, Node, SystemModel
from .test_planning import ObservationOption, TestPlan


@dataclass(frozen=True)
class DerivedAuthorizationReasoning:
    invariant: Invariant
    hypotheses: tuple[Hypothesis, ...]
    protected_functions: tuple[str, ...]
    unprotected_functions: tuple[str, ...]


def _contract_name(node: Node) -> str:
    return str(node.attributes.get("contract", node.label))


def _is_externally_callable(node: Node) -> bool:
    return str(node.attributes.get("visibility", "")) in {"external", "public"}


def _safe_identifier(value: str) -> str:
    return "".join(char if char.isalnum() else "_" for char in value).strip("_")


def _observation_id(function_id: str) -> str:
    return f"OBS-AUTH-{_safe_identifier(function_id)}"


def derive_authorization_reasoning(model: SystemModel) -> tuple[DerivedAuthorizationReasoning, ...]:
    """Infer competing authorization explanations from graph relationships."""
    functions = {node_id: node for node_id, node in model.nodes.items() if node.kind == "function" and _is_externally_callable(node)}
    writing_functions = {edge.source for edge in model.edges if edge.relation == "writes" and edge.source in functions}
    enforced = {edge.source: edge.target for edge in model.edges if edge.relation == "enforces" and edge.source in functions}

    by_contract: dict[str, list[str]] = {}
    for function_id in writing_functions:
        by_contract.setdefault(_contract_name(functions[function_id]), []).append(function_id)

    results: list[DerivedAuthorizationReasoning] = []
    for contract, function_ids in sorted(by_contract.items()):
        protected = tuple(sorted(function_id for function_id in function_ids if function_id in enforced))
        unprotected = tuple(sorted(function_id for function_id in function_ids if function_id not in enforced))
        if not protected or not unprotected:
            continue

        auth_ids = tuple(sorted(enforced[function_id] for function_id in protected))
        invariant_id = f"INV-SYS-AUTH-{_safe_identifier(contract)}"
        invariant = Invariant(
            invariant_id,
            f"Externally callable state-changing operations in {contract} must preserve the authorization boundary observed on protected sibling operations.",
            InvariantStatus.INFERRED,
            protected + unprotected + auth_ids,
            0.85,
            {"derivation": "sibling authorization boundary", "contract": contract},
        )
        hypotheses: list[Hypothesis] = []
        for function_id in unprotected:
            function_key = _safe_identifier(function_id)
            observation_id = _observation_id(function_id)
            hypotheses.extend((
                Hypothesis(
                    f"H-SYS-AUTH-{_safe_identifier(contract)}-{function_key}",
                    f"{function_id} may permit an unauthorized caller to mutate state despite the contract's observed authorization boundary.",
                    0.5,
                    HypothesisState.UNRESOLVED,
                    {observation_id: {"unauthorized mutation accepted": 1.0, "authorization enforced": 0.0}},
                ),
                Hypothesis(
                    f"H-SYS-ALT-{_safe_identifier(contract)}-{function_key}",
                    f"{function_id} may be protected by an alternate enforcement path that is not represented in the current system model.",
                    0.5,
                    HypothesisState.UNRESOLVED,
                    {observation_id: {"unauthorized mutation accepted": 0.0, "authorization enforced": 1.0}},
                ),
            ))
        results.append(DerivedAuthorizationReasoning(invariant, tuple(hypotheses), protected, unprotected))
    return tuple(results)


def plan_authorization_observations(reasoning: DerivedAuthorizationReasoning) -> tuple[TestPlan, ...]:
    """Rank observations using hypothesis-specific outcome predictions."""
    options = tuple(
        ObservationOption(
            _observation_id(function_id),
            f"Call {function_id} as an unauthorized caller and observe whether the state transition is accepted or rejected.",
            ("unauthorized mutation accepted", "authorization enforced"),
            1.0,
        )
        for function_id in reasoning.unprotected_functions
    )
    return rank_next_observations(reasoning.hypotheses, options)


def materialize_authorization_observations(model: SystemModel, reasoning: DerivedAuthorizationReasoning) -> tuple[TestPlan, ...]:
    """Persist ranked observations and explicit hypothesis/invariant bindings."""
    plans = plan_authorization_observations(reasoning)
    prospective = SystemModel.from_dict(model.export())
    invariant_id = f"invariant:{reasoning.invariant.invariant_id}"
    if invariant_id not in prospective.nodes:
        raise KeyError(f"derived invariant is not materialized: {invariant_id}")
    hypothesis_ids = tuple(f"hypothesis:{hypothesis.hypothesis_id}" for hypothesis in reasoning.hypotheses)
    for plan in plans:
        observation_id = f"observation:{plan.observation_id}"
        function_id = next(
            (candidate for candidate in reasoning.unprotected_functions if _observation_id(candidate) == plan.observation_id),
            None,
        )
        if function_id is None:
            raise KeyError(f"observation plan has no canonical target function: {plan.observation_id}")
        prospective.add_node(Node(observation_id, "observation", plan.description, {
            "status": "planned", "information_gain": plan.information_gain,
            "cost": plan.cost, "utility": plan.utility, "rationale": plan.rationale,
            "target_function_id": function_id, "provenance": "system_model_reasoning",
        }))
        prospective.add_edge(Edge(observation_id, "targets", invariant_id, {"provenance": "system_model_reasoning"}))
        for hypothesis_id in hypothesis_ids:
            prospective.add_edge(Edge(observation_id, "tests", hypothesis_id, {"provenance": "system_model_reasoning"}))
    from .graph_semantics import validate_graph
    errors = validate_graph(prospective)
    if errors:
        raise ValueError("invalid derived observation graph: " + "; ".join(errors))
    model.nodes = prospective.nodes
    model.edges = prospective.edges
    return plans


def materialize_authorization_reasoning(model: SystemModel) -> tuple[DerivedAuthorizationReasoning, ...]:
    """Persist derived invariant/hypothesis nodes and their provenance edges."""
    derived = derive_authorization_reasoning(model)
    prospective = SystemModel.from_dict(model.export())
    for item in derived:
        invariant_node_id = f"invariant:{item.invariant.invariant_id}"
        prospective.add_node(Node(invariant_node_id, "invariant", item.invariant.statement, {
            "status": item.invariant.status.value, "confidence": item.invariant.confidence,
            "source_ids": list(item.invariant.source_ids), "provenance": "system_model_reasoning",
        }))
        for hypothesis in item.hypotheses:
            hypothesis_node_id = f"hypothesis:{hypothesis.hypothesis_id}"
            prospective.add_node(Node(hypothesis_node_id, "hypothesis", hypothesis.statement, {
                "belief": hypothesis.belief, "state": hypothesis.state.value,
                "invariant_id": invariant_node_id, "provenance": "system_model_reasoning",
            }))
            prospective.add_edge(Edge(invariant_node_id, "informs", hypothesis_node_id, {"provenance": "system_model_reasoning"}))
    from .graph_semantics import validate_graph
    errors = validate_graph(prospective)
    if errors:
        raise ValueError("invalid derived reasoning graph: " + "; ".join(errors))
    model.nodes = prospective.nodes
    model.edges = prospective.edges
    return derived
