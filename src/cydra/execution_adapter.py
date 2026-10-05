from __future__ import annotations

"""Target-independent execution boundary for CYDRA experiments."""

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
    action_id: str
    operation: str
    inputs: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AdapterObservation:
    status: AdapterStatus
    action_id: str
    value: Any = None
    evidence: tuple[Mapping[str, Any], ...] = ()
    error: str | None = None


class ExecutionAdapter(Protocol):
    adapter_id: str
    def capabilities(self) -> tuple[AdapterCapability, ...]: ...
    def execute(self, request: AdapterRequest) -> AdapterObservation: ...
