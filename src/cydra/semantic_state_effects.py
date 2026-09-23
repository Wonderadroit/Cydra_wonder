from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from .ast_dataflow import SemanticRelationshipEvidence


@dataclass(frozen=True)
class StateEffect:
    """Canonical compiler-backed state effect for one function/state pair."""

    contract: str
    function: str
    state: str
    relation: str
    confidence: float
    provenance: str


_CANONICAL_RELATIONS = {"reads", "writes", "transition_expression"}


def build_state_effect_index(
    evidence: Iterable[SemanticRelationshipEvidence],
) -> dict[tuple[str, str], tuple[StateEffect, ...]]:
    """Index compiler-backed state effects by function.

    Only canonical semantic relations are consumed. Legacy ``reference`` evidence
    is deliberately ignored because it establishes identity, not mutation semantics.
    """
    grouped: dict[tuple[str, str], list[StateEffect]] = defaultdict(list)
    for item in evidence:
        if item.relation not in _CANONICAL_RELATIONS:
            continue
        effect = StateEffect(
            contract=item.contract,
            function=item.function,
            state=item.target,
            relation=item.relation,
            confidence=item.confidence,
            provenance=item.source,
        )
        key = (item.contract, item.function)
        if effect not in grouped[key]:
            grouped[key].append(effect)
    # Calls are kept separate from canonical state effects, but compiler-
    # resolved intra-contract calls allow their state effects to propagate to
    # the caller. This is a transitive closure: A -> B -> C inherits C's
    # state reads/writes without treating an unresolved or cross-contract call
    # as local state evidence.
    calls: dict[tuple[str, str], set[tuple[str, str]]] = defaultdict(set)
    for item in evidence:
        if item.relation != "calls":
            continue
        target_contract = None
        target_function = item.target
        metadata = item.metadata or {}
        if isinstance(metadata.get("target_contract"), str):
            target_contract = metadata["target_contract"]
        if isinstance(metadata.get("target_function"), str):
            target_function = metadata["target_function"]
        elif "." in target_function:
            target_contract, target_function = target_function.rsplit(".", 1)
        if target_contract is None:
            continue
        if target_contract != item.contract:
            continue
        calls[(item.contract, item.function)].add((target_contract, target_function))

    resolved = {name: list(items) for name, items in grouped.items()}
    changed = True
    while changed:
        changed = False
        for caller, callees in calls.items():
            bucket = resolved.setdefault(caller, [])
            known = {(item.state, item.relation) for item in bucket}
            for callee in callees:
                for effect in resolved.get(callee, ()): 
                    key = (effect.state, effect.relation)
                    if key in known:
                        continue
                    bucket.append(StateEffect(
                        contract=effect.contract,
                        function=caller[1],
                        state=effect.state,
                        relation=effect.relation,
                        confidence=min(effect.confidence, 0.95),
                        provenance=f"{effect.provenance}; transitive-call:{callee[0]}.{callee[1]}",
                    ))
                    known.add(key)
                    changed = True

    return {name: tuple(items) for name, items in resolved.items()}


def state_writes_for_function(
    effects: dict[tuple[str, str], tuple[StateEffect, ...]],
    function: str,
    contract: str = "",
) -> tuple[str, ...] | None:
    """Return authoritative state roots, or None when no compiler evidence exists."""
    items = effects.get((contract, function)) if contract else None
    if items is None and not contract:
        matches = [item for (item_contract, item_function), values in effects.items() if item_function == function for item in values]
        items = tuple(matches) if matches else None
    if items is None:
        return None
    writes = {
        item.state
        for item in items
        if item.relation in {"writes", "transition_expression"}
    }
    return tuple(sorted(writes))


def state_reads_for_function(
    effects: dict[tuple[str, str], tuple[StateEffect, ...]],
    function: str,
    contract: str = "",
) -> tuple[str, ...] | None:
    """Return compiler-backed state reads, optionally qualified by contract."""
    items = effects.get((contract, function)) if contract else None
    if items is None and not contract:
        matches = [
            item
            for (item_contract, item_function), values in effects.items()
            if item_function == function
            for item in values
        ]
        items = tuple(matches) if matches else None
    if items is None:
        return None
    return tuple(sorted({item.state for item in items if item.relation in {"reads", "transition_expression"}}))
