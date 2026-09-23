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
        caller_key = f"{item.contract}::{item.function}"
        if item.relation in _CANONICAL_RELATIONS:
            effect = StateEffect(
                contract=item.contract,
                function=item.function,
                state=item.target,
                relation=item.relation,
                confidence=item.confidence,
                provenance=item.source,
            )
            if effect not in grouped[caller_key]:
                grouped[caller_key].append(effect)
        elif item.relation == "calls":
            target_contract = (
                str(item.metadata.get("target_contract"))
                if isinstance(item.metadata, dict) and item.metadata.get("target_contract")
                else item.contract
            )
            calls[caller_key].add(f"{target_contract}::{item.target}")

    # Fixed-point propagation is bounded by the finite compiler evidence graph.
    # Propagate both reads and writes: a caller that delegates to a helper inherits
    # the helper's state effects for readiness and setup reasoning.
    changed = True
    while changed:
        changed = False
        for caller, callees in calls.items():
            caller_contract, caller_function = caller.split("::", 1)
            for callee in callees:
                for effect in grouped.get(callee, ()):
                    propagated = StateEffect(
                        contract=caller_contract,
                        function=caller_function,
                        state=effect.state,
                        relation=effect.relation,
                        confidence=min(effect.confidence, 0.95),
                        provenance=f"{effect.provenance}:via-call:{callee}",
                    )
                    if propagated not in grouped[caller]:
                        grouped[caller].append(propagated)
                        changed = True

    return {name: tuple(items) for name, items in grouped.items()}


def _effects_for_function(
    effects: dict[str, tuple[StateEffect, ...]],
    function: str,
    contract: str | None = None,
) -> tuple[StateEffect, ...] | None:
    if contract is not None:
        return effects.get(f"{contract}::{function}")
    matches = [items for key, items in effects.items() if key.endswith(f"::{function}")]
    if len(matches) != 1:
        # Ambiguous function names must fail closed rather than mixing state
        # effects from unrelated contracts.
        return None
    return matches[0]


def state_writes_for_function(
    effects: dict[str, tuple[StateEffect, ...]],
    function: str,
    contract: str | None = None,
) -> tuple[str, ...] | None:
    """Return authoritative direct/transitive state roots, or None when unavailable."""
    items = _effects_for_function(effects, function, contract)
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
    contract: str | None = None,
) -> tuple[str, ...] | None:
    """Return compiler-backed direct/transitive state reads, or None when unavailable."""
    items = _effects_for_function(effects, function, contract)
    if items is None:
        return None
    return tuple(sorted({item.state for item in items if item.relation in {"reads", "transition_expression"}}))
