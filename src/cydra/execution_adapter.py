from __future__ import annotations

"""Target-independent execution boundary for CYDRA experiments.

The reasoning engine decides *what* should be tested. An adapter decides *how*
that experiment can be executed against a particular technology stack.
Adapters must fail closed: inability to execute is capability evidence, never
security evidence.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Protocol


class AdapterStatus(str, Enum):
    EXECUTED = "executed"
    UNAVAILABLE = "unavailable"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass(frozen=True)
class AdapterCapability:
    name: str
    available: bool
    detail: str = ""


@dataclass(frozen=True)
class AdapterRequest:
    """Technology-neutral action passed from planning to an execution adapter."""

    action_id: str
    operation: str
    inputs: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AdapterObservation:
    """Immutable observation returned by an adapter."""

    status: AdapterStatus
    action_id: str
    value: Any = None
    evidence: tuple[Mapping[str, Any], ...] = ()
    error: str | None = None


class ExecutionAdapter(Protocol):
    """Minimal contract shared by Web2, EVM, and future execution adapters."""

    adapter_id: str

    def capabilities(self) -> tuple[AdapterCapability, ...]:
        ...

    def execute(self, request: AdapterRequest) -> AdapterObservation:
        ...
