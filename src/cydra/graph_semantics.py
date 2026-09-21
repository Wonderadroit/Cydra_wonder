from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Tuple

from .system_model import SystemModel

RELATION_RULES: Dict[str, Tuple[FrozenSet[str], FrozenSet[str]]] = {
    "supports": (frozenset({"evidence", "causal_chain"}), frozenset({"hypothesis", "evidence"})),
    "contradicts": (frozenset({"evidence", "hypothesis", "causal_chain"}), frozenset({"evidence", "hypothesis", "causal_chain"})),
    "explains": (frozenset({"causal_chain"}), frozenset({"evidence", "hypothesis"})),
    "derived_from": (frozenset({"evidence"}), frozenset({"observation", "evidence"})),
    "produced": (frozenset({"observation"}), frozenset({"evidence"})),
    "tests": (frozenset({"observation"}), frozenset({"hypothesis"})),
    "targets": (frozenset({"observation"}), frozenset({"invariant"})),
    "tested_by": (frozenset({"hypothesis", "invariant"}), frozenset({"observation"})),
    "informs": (frozenset({"invariant", "evidence"}), frozenset({"hypothesis", "evidence", "invariant"})),
    "verified_by": (frozenset({"invariant"}), frozenset({"evidence"})),
    "contradicted_by": (frozenset({"invariant"}), frozenset({"evidence"})),
    "updates": (frozenset({"observation", "evidence", "invariant", "causal_chain"}), frozenset({"belief"})),
    "updated_by": (frozenset({"evidence"}), frozenset({"evidence"})),
    "updated_to": (frozenset({"hypothesis"}), frozenset({"belief"})),
    "motivates": (frozenset({"hypothesis"}), frozenset({"causal_chain"})),
    "plans": (frozenset({"causal_chain"}), frozenset({"observation"})),
    "produced_evidence": (frozenset({"observation"}), frozenset({"evidence"})),
    "supported_by": (frozenset({"finding"}), frozenset({"evidence"})),
    "traced_by": (frozenset({"finding"}), frozenset({"causal_chain"})),
    "about": (frozenset({"finding"}), frozenset({"hypothesis"})),
    "has_resolution_plan": (frozenset({"evidence"}), frozenset({"evidence"})),
    "selects_observation": (frozenset({"evidence"}), frozenset({"observation"})),
    "re_evaluated_by": (frozenset({"evidence"}), frozenset({"evidence"})),
    "based_on": (frozenset({"evidence"}), frozenset({"evidence"})),
    "contains": (frozenset({"file", "module", "class"}), frozenset({"module", "class", "function"})),
    "imports": (frozenset({"module"}), frozenset({"import"})),
    "exposes": (frozenset({"function"}), frozenset({"entry_point"})),
    "uses_authorization": (frozenset({"module"}), frozenset({"authorization"})),
    "enforces": (frozenset({"function"}), frozenset({"authorization"})),
    "defined_in": (frozenset({"function", "state_variable"}), frozenset({"contract"})),
    "reads": (frozenset({"function"}), frozenset({"state_variable", "data_flow"})),
    "writes": (frozenset({"function"}), frozenset({"state_variable", "data_flow"})),
    "external_call": (frozenset({"function"}), frozenset({"data_flow", "function"})),
    "feeds": (frozenset({"contract", "module", "function"}), frozenset({"contract", "module", "function"})),
}

@dataclass(frozen=True)
class SemanticIssue:
    source: str
    relation: str
    target: str
    reason: str

def validate_semantics(model: SystemModel) -> List[SemanticIssue]:
    issues: List[SemanticIssue] = []
    for edge in model.edges:
        source = model.nodes.get(edge.source)
        target = model.nodes.get(edge.target)
        if source is None or target is None:
            continue
        rule = RELATION_RULES.get(edge.relation)
        if rule is None:
            issues.append(SemanticIssue(edge.source, edge.relation, edge.target, "unknown relationship type"))
            continue
        allowed_sources, allowed_targets = rule
        if source.kind not in allowed_sources:
            issues.append(SemanticIssue(edge.source, edge.relation, edge.target, f"source kind '{source.kind}' is not allowed"))
        if target.kind not in allowed_targets:
            issues.append(SemanticIssue(edge.source, edge.relation, edge.target, f"target kind '{target.kind}' is not allowed"))
    return issues

def validate_graph(model: SystemModel) -> List[str]:
    errors = list(model.validate())
    errors.extend(f"{i.source} -[{i.relation}]-> {i.target}: {i.reason}" for i in validate_semantics(model))
    return errors

def contradiction_pairs(model: SystemModel) -> List[Tuple[str, str]]:
    return sorted({tuple(sorted((e.source, e.target))) for e in model.edges if e.relation == "contradicts"})
