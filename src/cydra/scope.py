"""CYDRA scope and authorization gateway.

This module only classifies and enforces declared scope. It does not perform
active security testing. Unknown authorization is intentionally fail-closed.
"""

from dataclasses import dataclass, field
from enum import Enum
from fnmatch import fnmatch
from typing import Iterable


class ScopeState(str, Enum):
    IN_SCOPE = "IN_SCOPE"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    CONDITIONAL = "CONDITIONAL"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ScopeRule:
    pattern: str
    state: ScopeState
    reason: str = ""
    conditions: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScopeDecision:
    target: str
    state: ScopeState
    allowed_for_active_testing: bool
    reason: str
    matched_rule: str | None = None
    unresolved_conditions: tuple[str, ...] = ()


@dataclass
class ScopePolicy:
    rules: list[ScopeRule] = field(default_factory=list)
    default_state: ScopeState = ScopeState.UNKNOWN

    def decide(self, target: str, satisfied_conditions: Iterable[str] = ()) -> ScopeDecision:
        satisfied = set(satisfied_conditions)
        matches = [r for r in self.rules if fnmatch(target, r.pattern)]
        rule = matches[-1] if matches else None
        state = rule.state if rule else self.default_state
        reason = rule.reason if rule else "No explicit scope rule matched"
        unresolved: tuple[str, ...] = ()

        if rule and state is ScopeState.CONDITIONAL:
            unresolved = tuple(c for c in rule.conditions if c not in satisfied)
            allowed = not unresolved
            if not allowed:
                reason = reason or "Conditional scope requirements are not satisfied"
        else:
            allowed = state is ScopeState.IN_SCOPE

        return ScopeDecision(
            target=target,
            state=state,
            allowed_for_active_testing=allowed,
            reason=reason,
            matched_rule=rule.pattern if rule else None,
            unresolved_conditions=unresolved,
        )

    def require_active_testing(self, target: str, satisfied_conditions: Iterable[str] = ()) -> ScopeDecision:
        decision = self.decide(target, satisfied_conditions)
        if not decision.allowed_for_active_testing:
            raise ScopeViolation(decision)
        return decision


class ScopeViolation(PermissionError):
    """Raised when active testing is not established as authorized/in-scope."""

    def __init__(self, decision: ScopeDecision):
        self.decision = decision
        super().__init__(
            f"Active testing blocked for {decision.target!r}: "
            f"scope={decision.state.value}; {decision.reason}"
        )
