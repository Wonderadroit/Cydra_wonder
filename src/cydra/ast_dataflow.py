from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator


@dataclass(frozen=True)
class SemanticRelationshipEvidence:
    """A compiler-AST-backed relationship; never inferred from co-occurrence."""
    contract: str
    function: str
    relation: str
    target: str
    confidence: float
    source: str
    ast_node_id: int | None = None
    source_location: tuple[int, int, int] | None = None
    function_ast_node_id: int | None = None
    target_ast_node_id: int | None = None
    metadata: dict[str, Any] | None = None


def _walk(node: Any) -> Iterator[dict[str, Any]]:
    if isinstance(node, dict):
        if isinstance(node.get("nodeType"), str):
            yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def _location(node: dict[str, Any]) -> tuple[int, int, int] | None:
    src = node.get("src")
    if not isinstance(src, str):
        return None
    parts = src.split(":")
    if len(parts) != 3:
        return None
    try:
        return int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return None


def _node_id(node: Any) -> int | None:
    value = node.get("id") if isinstance(node, dict) else None
    return value if isinstance(value, int) else None


def _state_refs(node: Any, states: dict[int, str]) -> list[dict[str, Any]]:
    return [item for item in _walk(node)
            if item.get("nodeType") == "Identifier"
            and isinstance(item.get("referencedDeclaration"), int)
            and item["referencedDeclaration"] in states]


def _mark_lvalue_roles(node: Any, states: dict[int, str], roles: dict[int, str], role: str) -> None:
    """Mark the storage-root state reference; index/member expressions remain reads."""
    refs = _state_refs(node, states)
    if not refs:
        return
    first = _node_id(refs[0])
    if first is not None:
        roles[first] = role
    for ref in refs[1:]:
        ref_id = _node_id(ref)
        if ref_id is not None and ref_id not in roles:
            roles[ref_id] = "read"


def _operator_contexts(body: dict[str, Any], states: dict[int, str]) -> dict[int, str]:
    roles: dict[int, str] = {}
    for node in _walk(body):
        if node.get("nodeType") == "Assignment":
            operator = node.get("operator")
            if operator == "=":
                _mark_lvalue_roles(node.get("leftHandSide"), states, roles, "write")
            elif isinstance(operator, str):
                _mark_lvalue_roles(node.get("leftHandSide"), states, roles, "read_write")
        elif node.get("nodeType") == "UnaryOperation" and node.get("operator") in {"++", "--", "delete"}:
            _mark_lvalue_roles(node.get("subExpression"), states, roles,
                                "read_write" if node.get("operator") in {"++", "--"} else "write")
    return roles


def extract_ast_relationships(ast: dict[str, Any], file: str) -> list[SemanticRelationshipEvidence]:
    """Extract compiler-linked state reads/writes from AST operator context.

    Declaration IDs are authoritative. Canonical SystemModel relation names are used
    for projection: ``reads``, ``writes`` and ``transition_expression``. The precise
    semantic role is also retained in edge metadata, so read/write context is never lost.
    """
    declarations: dict[int, dict[str, Any]] = {}
    states: dict[int, str] = {}
    for node in _walk(ast):
        node_id = node.get("id")
        if isinstance(node_id, int):
            declarations[node_id] = node
        if node.get("nodeType") == "VariableDeclaration" and node.get("stateVariable") is True:
            if isinstance(node.get("name"), str) and isinstance(node_id, int):
                states[node_id] = node["name"]

    evidence: list[SemanticRelationshipEvidence] = []
    for node in _walk(ast):
        if node.get("nodeType") != "FunctionDefinition" or not isinstance(node.get("id"), int):
            continue
        function_id = node["id"]
        kind = node.get("kind")
        function_name = (node.get("name") if isinstance(node.get("name"), str) and node.get("name")
                         else kind if kind in {"constructor", "receive", "fallback"} else "anonymous")
        scope = node.get("scope")
        contract = declarations.get(scope, {}).get("name", "unknown") if isinstance(scope, int) else "unknown"
        body = node.get("body")
        if not isinstance(body, dict):
            continue
        roles = _operator_contexts(body, states)
        for item in _walk(body):
            if item.get("nodeType") != "Identifier":
                continue
            ref = item.get("referencedDeclaration")
            if not isinstance(ref, int) or ref not in states:
                continue
            item_id = _node_id(item)
            semantic_role = roles.get(item_id, "read") if item_id is not None else "read"
            relation = {"read": "reads", "write": "writes", "read_write": "transition_expression"}[semantic_role]
            common = dict(contract=str(contract), function=str(function_name), relation=relation,
                          target=states[ref], confidence=0.98 if item_id in roles else 0.90,
                          source=f"solc-json-ast:{file}", ast_node_id=item_id,
                          source_location=_location(item), function_ast_node_id=function_id,
                          target_ast_node_id=ref,
                          metadata={"function_kind": kind, "semantic_relation": semantic_role})
            evidence.append(SemanticRelationshipEvidence(**common))
            evidence.append(SemanticRelationshipEvidence(
                **{**common, "relation": "reference", "confidence": 0.90,
                   "metadata": {"function_kind": kind, "semantic_relation": semantic_role}}))
# Attribute state effects of same-source internal calls to their callers. A
    # public setter that delegates its storage mutation to a private/internal
    # helper still changes that state; omitting this edge can hide protected
    # state transitions from authorization reasoning. Keep this conservative:
    # only direct identifier calls resolving to a FunctionDefinition in this
    # AST are propagated (not arbitrary external/member calls).
    function_nodes = {
        node["id"]: node
        for node in _walk(ast)
        if node.get("nodeType") == "FunctionDefinition" and isinstance(node.get("id"), int)
    }
    function_names = {
        function_id: (
            node.get("name") if isinstance(node.get("name"), str) and node.get("name")
            else node.get("kind", "anonymous")
        )
        for function_id, node in function_nodes.items()
    }
    calls_by_function: dict[int, set[int]] = {function_id: set() for function_id in function_nodes}
    for function_id, node in function_nodes.items():
        body = node.get("body")
        if not isinstance(body, dict):
            continue
        for call in _walk(body):
            if call.get("nodeType") != "FunctionCall":
                continue
            expression = call.get("expression")
            if not isinstance(expression, dict) or expression.get("nodeType") != "Identifier":
                continue
            callee_id = expression.get("referencedDeclaration")
            if isinstance(callee_id, int) and callee_id in function_nodes and callee_id != function_id:
                calls_by_function[function_id].add(callee_id)

    # Fixed-point closure handles helper chains while the seen key prevents
    # recursive internal calls from producing duplicate or unbounded evidence.
    seen_effects = {
        (item.function_ast_node_id, item.relation, item.target, item.target_ast_node_id)
        for item in evidence
        if item.relation != "reference"
    }
    changed = True
    while changed:
        changed = False
        for caller_id, callees in calls_by_function.items():
            caller = function_nodes[caller_id]
            caller_kind = caller.get("kind")
            caller_name = function_names[caller_id]
            for callee_id in callees:
                call_sites = []
                body = caller.get("body")
                if isinstance(body, dict):
                    for call in _walk(body):
                        expression = call.get("expression")
                        if (
                            call.get("nodeType") == "FunctionCall"
                            and isinstance(expression, dict)
                            and expression.get("nodeType") == "Identifier"
                            and expression.get("referencedDeclaration") == callee_id
                        ):
                            call_sites.append(call)
                callee_effects = [
                    item for item in evidence
                    if item.function_ast_node_id == callee_id
                    and item.relation in {"reads", "writes", "transition_expression"}
                ]
                for call_site in call_sites:
                    for effect in callee_effects:
                        key = (caller_id, effect.relation, effect.target, effect.target_ast_node_id)
                        if key in seen_effects:
                            continue
                        seen_effects.add(key)
                        inherited = (effect.metadata or {}).get("propagated_from_internal_call")
                        propagated_from = inherited or function_names[callee_id]
                        evidence.append(SemanticRelationshipEvidence(
                            contract=str(
                                declarations.get(caller.get("scope"), {}).get("name", "unknown")
                                if isinstance(caller.get("scope"), int) else "unknown"
                            ),
                            function=str(caller_name),
                            relation=effect.relation,
                            target=effect.target,
                            confidence=min(effect.confidence, 0.94),
                            source=f"solc-json-ast-internal-call:{file}",
                            ast_node_id=_node_id(call_site),
                            source_location=_location(call_site),
                            function_ast_node_id=caller_id,
                            target_ast_node_id=effect.target_ast_node_id,
                            metadata={
                                "function_kind": caller_kind,
                                "semantic_relation": (effect.metadata or {}).get("semantic_relation", effect.relation),
                                "propagated_from_internal_call": propagated_from,
                                "propagation": "transitive-internal-call" if inherited else "internal-call",
                            },
                        ))
                        changed = True
    return evidence


