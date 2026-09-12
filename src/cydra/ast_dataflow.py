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


def extract_ast_relationships(ast: dict[str, Any], file: str) -> list[SemanticRelationshipEvidence]:
    """Conservatively extract compiler-linked state relationships.

    This migration shim intentionally emits only relationships whose declaration IDs
    are explicit in the compiler AST. Unsupported constructs remain absent rather than
    being reconstructed from lexical coincidence.
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
        if isinstance(node.get("name"), str) and node.get("name"):
            function_name = node["name"]
        elif kind == "constructor":
            function_name = "constructor"
        elif kind == "receive":
            function_name = "receive"
        elif kind == "fallback":
            function_name = "fallback"
        else:
            function_name = "anonymous"
        scope = node.get("scope")
        contract = declarations.get(scope, {}).get("name", "unknown") if isinstance(scope, int) else "unknown"
        body = node.get("body")
        if not isinstance(body, dict):
            continue
        for item in _walk(body):
            if item.get("nodeType") != "Identifier":
                continue
            ref = item.get("referencedDeclaration")
            if not isinstance(ref, int) or ref not in states:
                continue
            evidence.append(SemanticRelationshipEvidence(
                contract=str(contract), function=str(function_name), relation="reference",
                target=states[ref], confidence=0.90, source=f"solc-json-ast:{file}",
                ast_node_id=item.get("id") if isinstance(item.get("id"), int) else None,
                source_location=_location(item), function_ast_node_id=function_id,
                target_ast_node_id=ref,
                metadata={"function_kind": kind},
            ))
    return evidence
