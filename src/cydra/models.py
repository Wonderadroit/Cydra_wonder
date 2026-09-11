from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

EvidenceKind = Literal["source", "model", "analysis", "execution", "benchmark"]
EvidenceVerification = Literal["static_plus_execution", "dynamic_provenance"]
HypothesisStatus = Literal["proposed", "supported", "rejected", "confirmed"]


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    kind: EvidenceKind
    claim: str
    source: str
    location: str | None = None
    payload: dict[str, object] | None = None
    source_verification: EvidenceVerification | None = None


@dataclass(frozen=True)
class FunctionModel:
    name: str
    visibility: str
    modifiers: tuple[str, ...]
    writes: tuple[str, ...]
    external_calls: tuple[str, ...]
    line: int


@dataclass(frozen=True)
class ContractModel:
    name: str
    source: str
    functions: tuple[FunctionModel, ...]


@dataclass(frozen=True)
class Invariant:
    invariant_id: str
    statement: str
    provenance: str
    confidence: float


@dataclass(frozen=True)
class Hypothesis:
    hypothesis_id: str
    claim: str
    invariant_id: str
    target_function: str
    attacker_capability: str
    expected_impact: str
    status: HypothesisStatus = "proposed"
    evidence_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Experiment:
    experiment_id: str
    hypothesis_id: str
    action: str
    discriminates: tuple[str, ...]
    cost: float


@dataclass(frozen=True)
class InvestigationResult:
    target: str
    contracts: tuple[ContractModel, ...]
    invariants: tuple[Invariant, ...]
    hypotheses: tuple[Hypothesis, ...]
    experiments: tuple[Experiment, ...]
    evidence: tuple[Evidence, ...]
