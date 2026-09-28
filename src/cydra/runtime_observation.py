from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .models import ContractModel, FunctionModel


@dataclass(frozen=True)
class StateObservationPlan:
    """A deterministic source-backed runtime observation for one state predicate."""

    state: str
    getter: str
    expression: str
    predicate: str
    polarity: str
    source: str


def _public_mapping_getters(sources: tuple[str, ...]) -> set[str]:
    """Return public mapping state names using balanced declaration parsing."""
    getters: set[str] = set()
    for source in sources:
        for marker in re.finditer(r"\bmapping\s*\(", source):
            index = marker.end() - 1
            depth = 0
            while index < len(source):
                char = source[index]
                if char == "(":
                    depth += 1
                elif char == ")":
                    depth -= 1
                    if depth == 0:
                        break
                index += 1
            if depth != 0:
                continue
            declaration_end = source.find(";", index + 1)
            if declaration_end < 0:
                continue
            declaration = source[marker.start():declaration_end + 1]
            if not re.search(r"\bpublic\b", declaration):
                continue
            after_type = source[index + 1:declaration_end + 1]
            name_match = re.search(
                r"\b([A-Za-z_]\w*)\s*(?:=[^;]*)?;\s*$",
                after_type,
            )
            if name_match:
                getters.add(name_match.group(1))
    return getters


def _source_graph(contract: ContractModel) -> tuple[Path, ...]:
    """Return the target source plus reachable local Solidity imports.

    Public state may be declared in an inherited contract rather than the
    concrete target file. Observation planning must therefore inspect the
    source graph, while remaining fail-closed for unresolved imports.
    """
    root = Path(contract.source).resolve()
    seen: set[Path] = set()
    pending = [root]
    paths: list[Path] = []

    while pending:
        path = pending.pop()
        if path in seen:
            continue
        seen.add(path)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        paths.append(path)
        for match in re.finditer(r"""import\s+(?:[^"']+\s+from\s+)?["']([^"']+)["']\s*;""", text):
            imported = Path(match.group(1))
            candidate = (path.parent / imported).resolve()
            if candidate.exists():
                pending.append(candidate)

    return tuple(paths)


def plan_public_mapping_state_observations(
    contract: ContractModel,
    predicate: str,
) -> tuple[StateObservationPlan, ...]:
    """Plan a public mapping observation for a source-backed state predicate."""
    sources = _source_graph(contract)
    if not sources:
        return ()
    source_texts = tuple(
        path.read_text(encoding="utf-8")
        for path in sources
    )
    getters = _public_mapping_getters(source_texts)
    normalized = re.sub(r"\s+", " ", predicate).strip()

    # Positive mapping relation, optionally paired with a non-zero address guard.
    match = re.fullmatch(
        r"(?P<state>[A-Za-z_]\w*)\s*\[(?P<key>[^\]]+)\]\s*==\s*"
        r"(?P<value>[^&]+?)(?:\s*&&\s*(?P=state)\s*\[\s*(?P=key)\s*\]\s*!=\s*address\(0\))?",
        normalized,
    )
    if match and match.group("state") in getters:
        state = match.group("state")
        key = match.group("key").strip()
        value = match.group("value").strip()
        condition = f"target.{state}({key}) == {value}"
        return (StateObservationPlan(
            state=state,
            getter=f"target.{state}({key})",
            expression=condition,
            predicate=predicate,
            polarity="must_hold",
            source=f"{contract.source}:mapping",
        ),)

    # Default-false mapping guard.
    match = re.fullmatch(
        r"!\s*(?P<state>[A-Za-z_]\w*)\s*\[(?P<key>[^\]]+)\]",
        normalized,
    )
    if match and match.group("state") in getters:
        state = match.group("state")
        key = match.group("key").strip()
        condition = f"target.{state}({key}) == false"
        return (StateObservationPlan(
            state=state,
            getter=f"target.{state}({key})",
            expression=condition,
            predicate=predicate,
            polarity="must_hold",
            source=f"{contract.source}:mapping",
        ),)
    return ()


_PUBLIC_SCALAR_RE = re.compile(
    r"\b(?P<type>(?:uint\d*|int\d*|bool|address|bytes\d*))\s+"
    r"(?P<visibility>public)\s+(?P<name>[A-Za-z_]\w*)\s*(?:=[^;]*)?;"
)


def _public_scalar_getters(source: str) -> set[str]:
    """Return public scalar state names whose ABI getter takes no arguments."""
    return {match.group("name") for match in _PUBLIC_SCALAR_RE.finditer(source)}


def plan_public_state_observations(
    contract: ContractModel,
    function: FunctionModel,
) -> tuple[StateObservationPlan, ...]:
    """Plan fail-closed observations for directly observable scalar state predicates.

    This intentionally does not infer mappings, arrays, private storage, or
    compiler slots. If a predicate cannot be observed through a zero-argument
    public getter, no plan is emitted.
    """
    try:
        source = Path(contract.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ()

    getters = _public_scalar_getters(source)
    polarities = dict(function.state_predicate_polarities)
    plans: list[StateObservationPlan] = []

    # Direct scalar predicates remain the first observation surface.
    for predicate in function.state_predicates:
        polarity = polarities.get(predicate, "unknown")
        if polarity not in {"must_hold", "must_not_hold"}:
            continue
        match = re.fullmatch(
            r"\s*(?P<state>[A-Za-z_]\w*)\s*(?P<op>==|!=|>=|<=|>|<)\s*"
            r"(?P<literal>(?:0x[0-9A-Fa-f]+|\d+|true|false))\s*",
            predicate,
        )
        if not match or match.group("state") not in getters:
            continue
        state = match.group("state")
        condition = f"target.{state}() {match.group('op')} {match.group('literal')}"
        expression = condition if polarity == "must_hold" else f"!({condition})"
        plans.append(
            StateObservationPlan(
                state=state,
                getter=f"target.{state}()",
                expression=expression,
                predicate=predicate,
                polarity=polarity,
                source=f"{contract.source}:{function.line}",
            )
        )

    # Internal execution predicates are part of the target-derived state model.
    # Reuse the generic public-mapping observer for predicates reached through
    # the modeled same-contract call graph; never name a target-specific state.
    functions = {item.name: item for item in (*contract.functions, *contract.inherited_functions)}
    visited: set[str] = set()

    def visit(current) -> None:
        if current.name in visited:
            return
        visited.add(current.name)
        for predicate in current.execution_predicates:
            plans.extend(plan_public_mapping_state_observations(contract, predicate))
        # Follow same-contract calls from the source with brace-aware
        # function-body extraction. This mirrors the target model's provenance
        # without relying on a regex that terminates at an inner closing brace.
        try:
            source = Path(contract.source).read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return
        marker = re.search(rf"\bfunction\s+{re.escape(current.name)}\s*\([^)]*\)[^{{;]*{{", source)
        if marker:
            start = marker.end()
            depth = 1
            index = start
            while index < len(source) and depth:
                if source[index] == "{":
                    depth += 1
                elif source[index] == "}":
                    depth -= 1
                index += 1
            body = source[start:index - 1] if depth == 0 else ""
            seen_calls: set[str] = set()
            for call in re.finditer(r"\b([A-Za-z_]\w*)\s*\(", body):
                name = call.group(1)
                if name in seen_calls:
                    continue
                seen_calls.add(name)
                callee = functions.get(name)
                if callee is not None:
                    visit(callee)

    visit(function)
    return tuple(dict((plan.predicate, plan) for plan in plans).values())
