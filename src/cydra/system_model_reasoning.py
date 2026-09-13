"""Derive security-relevant reasoning from the canonical SystemModel.

This module is intentionally separate from the legacy vulnerability-class
heuristics. It treats the graph as the evidence substrate and derives an
authorization invariant from an observed sibling-function boundary rather
than from function names or a hard-coded modifier name.
"""
from __future__ import annotations

from dataclasses import dataclass

from .hypotheses import Hypothesis, HypothesisState
from .invariants import Invariant, InvariantStatus
from .system_model import Edge, Node, SystemModel


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


def derive_authorization_reasoning(model: SystemModel) -> tuple[DerivedAuthorizationReasoning, ...]:
    """Infer competing authorization explanations from graph relationships.

    A candidate is emitted only when the same contract contains both an
    externally callable state-changing function that enforces an observed
    authorization mechanism and another externally callable state-changing
    function that does not. The output deliberately contains two competing
    hypotheses for each unprotected function: a boundary-violation
    hypothesis and a benign/intended-public-interface alternative.
    """
    functions = {
        node_id: node
        for node_id, node in model.nodes.items()
        if node.kind == "function" and _is_externally_callable(node)
    }
    writing_functions = {
        edge.source
        for edge in model.edges
        if edge.relation == "writes" and edge.source in functions
    }
    enforced = {
        edge.source: edge.target
        for edge in model.edges
        if edge.relation == "enforces" and edge.source in functions
    }

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
        source_ids = protected + unprotected + auth_ids
        invariant_id = f"INV-SYS-AUTH-{_safe_identifier(contract)}"
        invariant = Invariant(
            invariant_id,
            f"Externally callable state-changing operations in {contract} must preserve the authorization boundary observed on protected sibling operations.",
            InvariantStatus.INFERRED,
            source_ids,
            0.85,
            {"derivation": "sibling authorization boundary", "contract": contract},
        )
        hypotheses: list[Hypothesis] = []
        for function_id in unprotected:
            function_key = _safe_identifier(function_id)
            hypotheses.extend((
                Hypothesis(
                    f"H-SYS-AUTH-{_safe_identifier(contract)}-{function_key}",
                    f"{function_id} may permit an unauthorized caller to mutate state despite the contract's observed authorization boundary.",
                    0.5,
                    HypothesisState.UNRESOLVED,
                    {"unauthorized_caller": {"support": 1.0, "authorized_only": 0.0}},
                ),
                Hypothesis(
                    f"H-SYS-PUBLIC-{_safe_identifier(contract)}-{function_key}",
                    f"{function_id} may be intentionally public, making the protected sibling boundary inapplicable to this state transition.",
                    0.5,
                    HypothesisState.UNRESOLVED,
                    {"intentional_public_interface": {"support": 1.0, "boundary_violation": 0.0}},
                ),
            ))
        results.append(DerivedAuthorizationReasoning(invariant, tuple(hypotheses), protected, unprotected))
    return tuple(results)


def materialize_authorization_reasoning(model: SystemModel) -> tuple[DerivedAuthorizationReasoning, ...]:
    """Persist derived invariant/hypothesis nodes and their provenance edges.

    Prospective validation is performed before mutation, so a malformed
    derivation cannot leave a partially materialized reasoning graph.
    """
    derived = derive_authorization_reasoning(model)
    prospective = SystemModel.from_dict(model.export())
    for item in derived:
        invariant_node_id = f"invariant:{item.invariant.invariant_id}"
        prospective.add_node(Node(invariant_node_id, "invariant", item.invariant.statement, {
            "status": item.invariant.status.value,
            "confidence": item.invariant.confidence,
            "source_ids": list(item.invariant.source_ids),
            "provenance": "system_model_reasoning",
        }))
        for hypothesis in item.hypotheses:
            hypothesis_node_id = f"hypothesis:{hypothesis.hypothesis_id}"
            prospective.add_node(Node(hypothesis_node_id, "hypothesis", hypothesis.statement, {
                "belief": hypothesis.belief,
                "state": hypothesis.state.value,
                "invariant_id": invariant_node_id,
                "provenance": "system_model_reasoning",
            }))
            prospective.add_edge(Edge(invariant_node_id, "informs", hypothesis_node_id, {"provenance": "system_model_reasoning"}))
    from .graph_semantics import validate_graph
    errors = validate_graph(prospective)
    if errors:
        raise ValueError("invalid derived reasoning graph: " + "; ".join(errors))
    model.nodes = prospective.nodes
    model.edges = prospective.edges
    return derived
