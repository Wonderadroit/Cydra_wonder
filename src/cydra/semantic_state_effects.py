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
    return {name: tuple(items) for name, items in grouped.items()}


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
    effects: dict[str, tuple[StateEffect, ...]],
    function: str,
) -> tuple[str, ...] | None:
    """Return compiler-backed state reads, or None when evidence is unavailable."""
    items = effects.get(function)
    if items is None:
        return None
    return tuple(sorted({item.state for item in items if item.relation in {"reads", "transition_expression"}}))
