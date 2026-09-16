from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator


@dataclass(frozen=True)
class ConstraintEvidence:
    """Compiler-linked input constraint observed on a function parameter.

    This records the target's actual predicate without deciding whether a value is
    good or bad for a particular hypothesis. Experiment planning may interpret the
    predicate later; extraction itself stays class-neutral.
    """

    contract: str
    function: str
    parameter: str
    parameter_index: int
    predicate: str
    source: str
    ast_node_id: int | None = None
    source_location: tuple[int, int, int] | None = None
    kind: str = "precondition"


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


def _expr(node: Any, names: dict[int, str]) -> str:
    if not isinstance(node, dict):
        return ""
    kind = node.get("nodeType")
    if kind == "Identifier":
        ref = node.get("referencedDeclaration")
        if isinstance(ref, int) and ref in names:
            return names[ref]
        name = node.get("name")
        return str(name) if isinstance(name, str) else ""
    if kind == "Literal":
        value = node.get("value")
        if isinstance(value, str):
            return value
        hex_value = node.get("hexValue")
        return str(hex_value) if isinstance(hex_value, str) else ""
    if kind == "BinaryOperation":
        left = _expr(node.get("leftExpression"), names)
        right = _expr(node.get("rightExpression"), names)
        op = node.get("operator")
        return f"{left} {op} {right}" if left and isinstance(op, str) and right else ""
    if kind == "UnaryOperation":
        operand = _expr(node.get("subExpression"), names)
        op = node.get("operator")
        return f"{op}{operand}" if operand and isinstance(op, str) else ""
    if kind == "FunctionCall":
        expression = _expr(node.get("expression"), names)
        args = [_expr(arg, names) for arg in node.get("arguments", ())]
        if expression and all(args):
            return f"{expression}({', '.join(args)})"
        return expression
    if kind == "MemberAccess":
        base = _expr(node.get("expression"), names)
        member = node.get("memberName")
        return f"{base}.{member}" if base and isinstance(member, str) else ""
    return ""


def _parameter_names(function: dict[str, Any]) -> dict[int, tuple[int, str]]:
    result: dict[int, tuple[int, str]] = {}
    params = function.get("parameters")
    if not isinstance(params, dict):
        return result
    items = params.get("parameters")
    if not isinstance(items, list):
        return result
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        node_id = item.get("id")
        name = item.get("name")
        if isinstance(node_id, int) and isinstance(name, str) and name:
            result[node_id] = (index, name)
    return result


def _contains_parameter(node: Any, parameter_ids: set[int]) -> bool:
    return any(item.get("nodeType") == "Identifier" and item.get("referencedDeclaration") in parameter_ids
               for item in _walk(node))


def _constraint_nodes(function: dict[str, Any]) -> Iterator[tuple[dict[str, Any], str]]:
    body = function.get("body")
    if not isinstance(body, dict):
        return
    for node in _walk(body):
        if node.get("nodeType") == "FunctionCall":
            expression = node.get("expression")
            if isinstance(expression, dict) and expression.get("nodeType") == "Identifier" and expression.get("name") == "require":
                arguments = node.get("arguments")
                if isinstance(arguments, list) and arguments:
                    yield arguments[0], "require"
        elif node.get("nodeType") == "IfStatement":
            condition = node.get("condition")
            true_body = node.get("trueBody")
            if isinstance(condition, dict) and isinstance(true_body, dict):
                if any(item.get("nodeType") in {"RevertStatement", "Throw"} for item in _walk(true_body)):
                    yield condition, "revert_guard"


def extract_parameter_constraints(ast: dict[str, Any], file: str) -> tuple[ConstraintEvidence, ...]:
    """Extract compiler-linked predicates that constrain function inputs.

    Only predicates that reference a declared parameter are emitted. The extractor
    deliberately preserves the predicate rather than guessing an allowed domain.
    """
    declarations = {node.get("id"): node for node in _walk(ast) if isinstance(node.get("id"), int)}
    evidence: list[ConstraintEvidence] = []
    for function in _walk(ast):
        if function.get("nodeType") != "FunctionDefinition":
            continue
        function_id = function.get("id")
        if not isinstance(function_id, int):
            continue
        params = _parameter_names(function)
        if not params:
            continue
        names = {node_id: name for node_id, (_, name) in params.items()}
        parameter_ids = set(params)
        scope = function.get("scope")
        contract = declarations.get(scope, {}).get("name", "unknown") if isinstance(scope, int) else "unknown"
        function_name = function.get("name") or function.get("kind") or "anonymous"
        if not isinstance(function_name, str):
            function_name = "anonymous"
        for predicate_node, kind in _constraint_nodes(function):
            if not _contains_parameter(predicate_node, parameter_ids):
                continue
            predicate = _expr(predicate_node, names)
            if not predicate:
                continue
            referenced = [item.get("referencedDeclaration") for item in _walk(predicate_node)
                          if item.get("nodeType") == "Identifier" and item.get("referencedDeclaration") in parameter_ids]
            for parameter_id in dict.fromkeys(referenced):
                index, name = params[parameter_id]
                evidence.append(ConstraintEvidence(
                    contract=str(contract), function=function_name, parameter=name,
                    parameter_index=index, predicate=predicate, source=f"solc-json-ast:{file}",
                    ast_node_id=predicate_node.get("id") if isinstance(predicate_node.get("id"), int) else None,
                    source_location=_location(predicate_node), kind=kind,
                ))
    return tuple(evidence)
