from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from .ast_dataflow import SemanticRelationshipEvidence


@dataclass(frozen=True)
class StateEffect:
    """Canonical compiler-backed state effect for one function/state pair."""

    function: str
    state: str
    relation: str
    confidence: float
    provenance: str


_CANONICAL_RELATIONS = {"reads", "writes", "transition_expression"}


def build_state_effect_index(
    evidence: Iterable[SemanticRelationshipEvidence],
) -> dict[str, tuple[StateEffect, ...]]:
    """Index compiler-backed direct and transitive state effects by function.

    Compiler AST evidence is the authority for direct effects. Resolved internal
    and inherited calls are then followed to expose state dependencies that are
    semantically real but occur below a producer (for example a value getter
    delegating to a balance accessor). This remains evidence, not satisfiability.
    """
    grouped: dict[str, list[StateEffect]] = defaultdict(list)
    calls: dict[str, set[str]] = defaultdict(set)

    for item in evidence:
        if item.relation in _CANONICAL_RELATIONS:
            effect = StateEffect(
                function=item.function,
                state=item.target,
                relation=item.relation,
                confidence=item.confidence,
                provenance=item.source,
            )
            if effect not in grouped[item.function]:
                grouped[item.function].append(effect)
        elif item.relation == "calls":
            calls[item.function].add(item.target)

    # Fixed-point propagation is bounded by the finite compiler evidence graph.
    # Propagate both reads and writes: a caller that delegates to a helper inherits
    # the helper's state effects for readiness and setup reasoning.
    changed = True
    while changed:
        changed = False
        for caller, callees in calls.items():
            for callee in callees:
                for effect in grouped.get(callee, ()):
                    propagated = StateEffect(
                        function=caller,
                        state=effect.state,
                        relation=effect.relation,
                        confidence=min(effect.confidence, 0.95),
                        provenance=f"{effect.provenance}:via-call:{callee}",
                    )
                    if propagated not in grouped[caller]:
                        grouped[caller].append(propagated)
                        changed = True

    return {name: tuple(items) for name, items in grouped.items()}


def state_writes_for_function(
    effects: dict[str, tuple[StateEffect, ...]],
    function: str,
) -> tuple[str, ...] | None:
    """Return authoritative direct/transitive state roots, or None when unavailable."""
    items = effects.get(function)
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
    """Return compiler-backed direct/transitive state reads, or None when unavailable."""
    items = effects.get(function)
    if items is None:
        return None
    return tuple(sorted({item.state for item in items if item.relation in {"reads", "transition_expression"}}))
