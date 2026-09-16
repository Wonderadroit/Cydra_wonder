from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .interface_resolver import ResolvedInterface

EvidenceKind = Literal["source", "model", "analysis", "execution", "benchmark"]
HypothesisStatus = Literal["proposed", "supported", "rejected", "confirmed"]


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    kind: EvidenceKind
    claim: str
    source: str
    location: str | None = None


@dataclass(frozen=True)
class ParameterModel:
    """Syntactically extracted Solidity parameter metadata.

    ``type`` preserves the declared Solidity type spelling. No semantic ABI
    resolution is performed at this layer; custom types therefore remain
    unresolved declarations rather than guessed ABI layouts.
    """

    name: str
    type: str
    data_location: str | None = None


@dataclass(frozen=True)
class ConstructorModel:
    parameters: tuple[ParameterModel, ...]
    line: int
    interface_casts: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    resolved_interface_casts: tuple[tuple[str, ResolvedInterface], ...] = field(default_factory=tuple)
    derived_interface_casts: tuple[tuple[str, str, ResolvedInterface], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class FunctionModel:
    name: str
    visibility: str
    modifiers: tuple[str, ...]
    writes: tuple[str, ...]
    external_calls: tuple[str, ...]
    line: int
    parameters: tuple[ParameterModel, ...] = field(default_factory=tuple)
    authorization_predicates: tuple[str, ...] = field(default_factory=tuple)
    state_predicates: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ContractModel:
    name: str
    source: str
    functions: tuple[FunctionModel, ...]
    constructor: ConstructorModel | None = None
    pragma: str | None = None
    state_variables: tuple[str, ...] = field(default_factory=tuple)
    inherits: tuple[str, ...] = field(default_factory=tuple)
    declared_types: tuple[str, ...] = field(default_factory=tuple)
    inherited_resolved_interfaces: tuple[ResolvedInterface, ...] = field(default_factory=tuple)


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
    # Ordered ABI arguments selected by the generic experiment-input planner.
    # Empty means no complete vector was safely planned and the generator may use
    # its existing conservative fallback.
    planned_inputs: tuple[str, ...] = field(default_factory=tuple)
    # Optional identity binding prevents a planned vector from being reused for a
    # different target function. Kept optional for compatibility with legacy plans.
    target_function: str | None = None


@dataclass(frozen=True)
class InvestigationResult:
    target: str
    contracts: tuple[ContractModel, ...]
    invariants: tuple[Invariant, ...]
    hypotheses: tuple[Hypothesis, ...]
    experiments: tuple[Experiment, ...]
    evidence: tuple[Evidence, ...]