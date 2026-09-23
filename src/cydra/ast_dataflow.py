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
    first = refs[0]
    first_id = _node_id(first)
    first_ref = first.get("referencedDeclaration")
    if isinstance(first_id, int):
        roles[first_id] = role
    if isinstance(first_ref, int):
        roles[first_ref] = role
    for ref in refs[1:]:
        ref_id = _node_id(ref)
        ref_decl = ref.get("referencedDeclaration")
        if isinstance(ref_id, int) and ref_id not in roles:
            roles[ref_id] = "read"
        if isinstance(ref_decl, int) and ref_decl not in roles:
            roles[ref_decl] = "read"


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
        elif node.get("nodeType") == "MemberAccess" and node.get("memberName") in {"push", "pop"}:
            # Array push/pop mutate the storage root through MemberAccess.
            _mark_lvalue_roles(
                node.get("expression"),
                states,
                roles,
                "write" if node.get("memberName") == "push" else "read_write",
            )
    return roles


def extract_ast_relationships(
    ast: dict[str, Any],
    file: str,
    *,
    global_functions: dict[int, tuple[str, str, int]] | None = None,
    global_contract_ancestors: dict[int, set[int]] | None = None,
) -> list[SemanticRelationshipEvidence]:
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

    # Build compiler-authoritative inheritance metadata and a function declaration index.
    # A derived contract can invoke an inherited internal/public function whose
    # declaration belongs to a base contract; preserve that compiler-resolved edge.
    contract_bases: dict[int, set[int]] = {}
    contract_names: dict[int, str] = {}
    for item in _walk(ast):
        if item.get("nodeType") != "ContractDefinition" or not isinstance(item.get("id"), int):
            continue
        contract_id = item["id"]
        contract_names[contract_id] = str(item.get("name", "unknown"))
        bases: set[int] = set()
        for base in item.get("baseContracts", []) if isinstance(item.get("baseContracts"), list) else []:
            base_name = base.get("baseName") if isinstance(base, dict) else None
            ref = base_name.get("referencedDeclaration") if isinstance(base_name, dict) else None
            if isinstance(ref, int):
                bases.add(ref)
        contract_bases[contract_id] = bases

    def _ancestor_contract_ids(contract_id: int, seen: set[int] | None = None) -> set[int]:
        seen = set() if seen is None else seen
        for base_id in contract_bases.get(contract_id, set()):
            if base_id in seen:
                continue
            seen.add(base_id)
            _ancestor_contract_ids(base_id, seen)
        return seen

    contract_ancestors = {
        contract_id: _ancestor_contract_ids(contract_id)
        for contract_id in contract_bases
    }

    # Build a compiler-authoritative function declaration index so internal
    # calls can be represented as data-flow edges. We intentionally resolve only
    # AST declarations present in this compiler unit; unresolved/dynamic calls
    # remain unresolved rather than being guessed from names.
    local_functions: dict[int, tuple[str, str, int]] = {}
    for item in _walk(ast):
        if item.get("nodeType") != "FunctionDefinition" or not isinstance(item.get("id"), int):
            continue
        scope = item.get("scope")
        contract_name = declarations.get(scope, {}).get("name", "unknown") if isinstance(scope, int) else "unknown"
        kind = item.get("kind")
        function_name = (
            item.get("name") if isinstance(item.get("name"), str) and item.get("name")
            else kind if kind in {"constructor", "receive", "fallback"} else "anonymous"
        )
        local_functions[item["id"]] = (str(contract_name), str(function_name), scope if isinstance(scope, int) else -1)
    functions = global_functions if global_functions is not None else local_functions
    ancestors = global_contract_ancestors if global_contract_ancestors is not None else contract_ancestors

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
        for call in _walk(body):
            if call.get("nodeType") != "FunctionCall":
                continue
            expression = call.get("expression")
            if not isinstance(expression, dict):
                continue
            declaration_id = expression.get("referencedDeclaration")
            if not isinstance(declaration_id, int) or declaration_id not in functions:
                continue
            target_contract, target_function, target_scope = functions[declaration_id]
            inherited_target = (
                isinstance(scope, int)
                and target_scope in ancestors.get(scope, set())
            )
            # Keep only compiler-resolved declarations. Calls to external or
            # dynamically resolved targets that lack a local declaration are
            # deliberately left unresolved for the higher-level readiness
            # model to handle conservatively.
            evidence.append(SemanticRelationshipEvidence(
                contract=str(contract), function=str(function_name), relation="calls",
                target=f"{target_contract}.{target_function}", confidence=0.98,
                source=f"solc-json-ast:{file}", ast_node_id=_node_id(call),
                source_location=_location(call), function_ast_node_id=function_id,
                target_ast_node_id=declaration_id,
                metadata={"function_kind": kind, "semantic_relation": "calls",
                          "target_contract": target_contract, "target_function": target_function,
                          "inherited_target": inherited_target},
            ))
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
