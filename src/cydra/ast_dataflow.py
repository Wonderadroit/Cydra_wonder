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


def extract_ast_relationships(\n    ast: dict[str, Any],\n    file: str,\n    known_state_declarations: dict[int, str] | None = None,\n) -> list[SemanticRelationshipEvidence]:
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

    if known_state_declarations:\n        states.update(known_state_declarations)\n\n    evidence: list[SemanticRelationshipEvidence] = []
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
    return evidence
