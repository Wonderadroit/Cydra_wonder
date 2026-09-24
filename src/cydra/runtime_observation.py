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


_PUBLIC_SCALAR_RE = re.compile(
    r"^\s*(?P<type>(?:uint\d*|int\d*|bool|address|bytes\d*))\s+"
    r"(?P<visibility>public)\s+(?P<name>[A-Za-z_]\w*)\s*(?:=[^;]*)?;$",
    re.MULTILINE,
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
    return tuple(plans)
