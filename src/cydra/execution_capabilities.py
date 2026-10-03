from __future__ import annotations

"""Generic experiment capability contracts and feasibility solving."""

from dataclasses import dataclass, field
from enum import Enum
import re

from .execution_readiness import ExecutionReadiness
from .models import ContractModel, Experiment, Hypothesis
from .experiment_inputs import prove_parameter_materialization

class CapabilityStatus(str, Enum):
    AVAILABLE = "available"
    PARTIAL = "partial"
    MISSING = "missing"
    BLOCKED = "blocked"

class Capability(str, Enum):
    CALLER_CONSTRUCTION = "CALLER_CONSTRUCTION"
    ROLE_ESTABLISHMENT = "ROLE_ESTABLISHMENT"
    STATE_SETUP = "STATE_SETUP"
    CONSTRUCTOR_SETUP = "CONSTRUCTOR_SETUP"
    CALLBACK_HARNESS = "CALLBACK_HARNESS"
    REENTRANCY_HARNESS = "REENTRANCY_HARNESS"
    VALUE_PROVISION = "VALUE_PROVISION"
    TOKEN_PROVISION = "TOKEN_PROVISION"
    BALANCE_PROVISION = "BALANCE_PROVISION"
    ADDRESS_PROVISION = "ADDRESS_PROVISION"
    PROXY_DEPLOYMENT = "PROXY_DEPLOYMENT"
    EVENT_OBSERVATION = "EVENT_OBSERVATION"
    STATE_OBSERVATION = "STATE_OBSERVATION"
    CALL_SEQUENCE = "CALL_SEQUENCE"
    INTERNAL_CALL_PROPAGATION = "INTERNAL_CALL_PROPAGATION"
    TYPE_MATERIALIZATION = "TYPE_MATERIALIZATION"

@dataclass(frozen=True)
class CapabilityRequirement:
    capability: Capability
    subject: str
    source: str
    detail: str = ""
    subcapability: str | None = None
    provenance: str | None = None

@dataclass(frozen=True)
class CapabilityAvailability:
    capability: Capability
    status: CapabilityStatus
    source: str
    subcapabilities: tuple[str, ...] = ()
    detail: str = ""

class MaterializationStage(str, Enum):
    SUBJECT = "subject"
    PREREQUISITES = "prerequisites"
    ATTACKER = "attacker"
    CALL_SEQUENCE = "call_sequence"
    OBSERVATIONS = "observations"
    OUTCOME = "outcome"


@dataclass(frozen=True)
class CapabilityGap:
    capability: Capability
    subject: str
    subcapability: str | None
    status: CapabilityStatus
    reason: str
    stage: MaterializationStage = MaterializationStage.PREREQUISITES
    failure_class: str = "capability"
    provenance: str | None = None


@dataclass(frozen=True)
class MaterializationFailure:
    """Structured evidence that an execution realization failed at a generic stage."""

    gap: CapabilityGap
    error_type: str
    message: str


def classify_materialization_failure(error: BaseException) -> MaterializationFailure:
    """Translate renderer/readiness failures into reusable capability-gap evidence."""
    message = str(error)
    error_type = type(error).__name__
    lowered = message.lower()

    if "nested struct type" in lowered or "struct fields" in lowered:
        match = re.search(r"(?:nested struct type|parameter type)\s+([A-Za-z_][\w.]*)", message)
        subject = match.group(1) if match else "custom struct"
        provenance_match = re.search(r"\sfrom\s+([^:]+(?:\.sol|/[^:]+))(?::|$)", message)
        provenance = provenance_match.group(1) if provenance_match else None
        gap = CapabilityGap(
            Capability.TYPE_MATERIALIZATION,
            subject,
            "nested_custom_struct",
            CapabilityStatus.BLOCKED,
            "custom nested struct could not be resolved/materialized",
            MaterializationStage.PREREQUISITES,
            "resolver",
            provenance,
        )
    elif "constructor" in lowered and ("unsupported" in lowered or "cannot" in lowered or "failed" in lowered):
        gap = CapabilityGap(
            Capability.CONSTRUCTOR_SETUP,
            "constructor",
            None,
            CapabilityStatus.BLOCKED,
            message,
            MaterializationStage.PREREQUISITES,
            "constructor_materialization",
        )
    elif "no deterministic public" in lowered or "state observation" in lowered:
        subcapability = "public_mapping" if "mapping" in lowered else "public_state_observation"
        gap = CapabilityGap(
            Capability.STATE_OBSERVATION,
            "state observation",
            subcapability,
            CapabilityStatus.BLOCKED,
            message,
            MaterializationStage.OBSERVATIONS,
            "observation_planner",
        )
    elif "arity mismatch" in lowered or "tuple arity" in lowered or "unsupported setup parameter type" in lowered:
        gap = CapabilityGap(
            Capability.TYPE_MATERIALIZATION,
            "parameter materialization",
            "tuple",
            CapabilityStatus.BLOCKED,
            message,
            MaterializationStage.PREREQUISITES,
            "type_materializer",
        )
    else:
        gap = CapabilityGap(
            Capability.CALL_SEQUENCE,
            "experiment materialization",
            None,
            CapabilityStatus.BLOCKED,
            message,
            MaterializationStage.CALL_SEQUENCE,
            "renderer",
        )
    return MaterializationFailure(gap, error_type, message)


@dataclass(frozen=True)
class ExperimentContract:
    """Normalized handoff from reasoning to execution realization."""
    experiment_id: str
    hypothesis_id: str
    target_function: str
    requirements: tuple[CapabilityRequirement, ...] = field(default_factory=tuple)

@dataclass(frozen=True)
class CapabilityResolution:
    contract: ExperimentContract
    availability: tuple[CapabilityAvailability, ...]
    gaps: tuple[CapabilityGap, ...] = field(default_factory=tuple)

    @property
    def executable(self) -> bool:
        return not self.gaps

    def by_capability(self) -> dict[str, dict[str, object]]:
        grouped: dict[str, dict[str, object]] = {}
        for requirement in self.contract.requirements:
            key = requirement.capability.value
            grouped.setdefault(key, {"required": [], "status": CapabilityStatus.AVAILABLE.value, "gaps": []})["required"].append(requirement.subject)
        for gap in self.gaps:
            item = grouped.setdefault(gap.capability.value, {"required": [], "status": gap.status.value, "gaps": []})
            item["status"] = gap.status.value
            item["gaps"].append({"subject": gap.subject, "subcapability": gap.subcapability, "reason": gap.reason, "stage": gap.stage.value, "failure_class": gap.failure_class, "provenance": gap.provenance})
        return grouped

def default_capability_availability() -> tuple[CapabilityAvailability, ...]:
    """Describe current generic execution surfaces; target readiness remains separate."""
    return (
        CapabilityAvailability(Capability.CALLER_CONSTRUCTION, CapabilityStatus.AVAILABLE, "execution_readiness"),
        CapabilityAvailability(Capability.ROLE_ESTABLISHMENT, CapabilityStatus.AVAILABLE, "execution_readiness"),
        CapabilityAvailability(Capability.STATE_SETUP, CapabilityStatus.PARTIAL, "execution_readiness"),
        CapabilityAvailability(Capability.CONSTRUCTOR_SETUP, CapabilityStatus.AVAILABLE, "sequence_foundry"),
        CapabilityAvailability(Capability.CALLBACK_HARNESS, CapabilityStatus.PARTIAL, "callback_state_order_execution"),
        CapabilityAvailability(Capability.REENTRANCY_HARNESS, CapabilityStatus.PARTIAL, "callback_state_order_execution"),
        CapabilityAvailability(Capability.VALUE_PROVISION, CapabilityStatus.PARTIAL, "execution_readiness"),
        CapabilityAvailability(Capability.TOKEN_PROVISION, CapabilityStatus.PARTIAL, "execution_readiness"),
        CapabilityAvailability(Capability.BALANCE_PROVISION, CapabilityStatus.PARTIAL, "execution_readiness"),
        CapabilityAvailability(Capability.ADDRESS_PROVISION, CapabilityStatus.AVAILABLE, "sequence_foundry"),
        CapabilityAvailability(Capability.PROXY_DEPLOYMENT, CapabilityStatus.PARTIAL, "initialization_execution"),
        CapabilityAvailability(Capability.EVENT_OBSERVATION, CapabilityStatus.AVAILABLE, "foundry"),
        CapabilityAvailability(Capability.STATE_OBSERVATION, CapabilityStatus.PARTIAL, "runtime_observation", ("public_scalar", "public_mapping", "state_relation")),
        CapabilityAvailability(Capability.CALL_SEQUENCE, CapabilityStatus.AVAILABLE, "sequence_foundry"),
        CapabilityAvailability(Capability.INTERNAL_CALL_PROPAGATION, CapabilityStatus.AVAILABLE, "execution_readiness"),
        CapabilityAvailability(Capability.TYPE_MATERIALIZATION, CapabilityStatus.PARTIAL, "sequence_foundry", ("primitive", "array", "tuple", "custom_struct", "nested_custom_struct", "namespaced_custom_struct")),
    )

def _custom_type(parameter_type: str) -> bool:
    base = parameter_type.strip().split()[0].rstrip('[]')
    return not (base in {'address', 'bool', 'string', 'bytes'} or base.startswith(('uint', 'int', 'bytes', 'fixed', 'ufixed')))

def _type_subcapability(parameter_type: str) -> str:
    base = parameter_type.strip().split()[0]
    if base.endswith('[]'):
        return 'array'
    if '.' in base:
        return 'namespaced_custom_struct'
    return 'custom_struct'

def build_experiment_contract(hypothesis: Hypothesis, experiment: Experiment, contract: ContractModel, readiness: ExecutionReadiness) -> ExperimentContract:
    if experiment.hypothesis_id != hypothesis.hypothesis_id:
        raise ValueError('experiment contract hypothesis mismatch')
    target_function = experiment.target_function or hypothesis.target_function
    if target_function != hypothesis.target_function:
        raise ValueError('experiment contract target function mismatch')
    requirements: list[CapabilityRequirement] = []
    def add(capability: Capability, subject: str, source: str, detail: str = '', subcapability: str | None = None, provenance: str | None = None) -> None:
        requirements.append(CapabilityRequirement(capability, subject, source, detail, subcapability, provenance))
    if readiness.caller_requirements:
        add(Capability.CALLER_CONSTRUCTION, 'caller requirements', 'execution_readiness')
    if readiness.constructor_requirements:
        add(Capability.CONSTRUCTOR_SETUP, 'constructor requirements', 'execution_readiness')
    # Capability requirements describe an actual execution gap, not merely the
    # existence of a readiness surface. A constructible setup candidate is
    # already consumable by the recursive state planner, and input/local
    # execution predicates are not state-observation gaps. Keeping this
    # distinction prevents a globally-partial capability registry from turning
    # every target with modeled state into BLOCKED_BY_CAPABILITY.
    unresolved_state_requirements = tuple(
        item for item in readiness.state_requirements
        if item.status in {"unresolved", "required"}
    )
    constructible_state_candidates = tuple(
        item for item in readiness.state_setup_candidates
        if item.status == "constructible"
    )
    if unresolved_state_requirements and not constructible_state_candidates:
        add(Capability.STATE_SETUP, 'persistent state prerequisites', 'execution_readiness')
    unresolved_state_observation = tuple(
        item for item in (
            *readiness.state_requirements,
            *readiness.execution_requirements,
        )
        if item.status in {"unresolved", "required"}
        and item.category == "state_observation"
    )
    if readiness.state_requirements or unresolved_state_observation:
        add(Capability.STATE_OBSERVATION, 'state/execution prerequisites', 'runtime_observation')
    if readiness.runtime_requirements:
        add(Capability.INTERNAL_CALL_PROPAGATION, 'internal call prerequisites', 'execution_readiness')
    if experiment.steps:
        add(Capability.CALL_SEQUENCE, 'ordered experiment steps', 'experiment')
    function = next((item for item in contract.functions if item.name == target_function), None)
    if function:
        for parameter in function.parameters:
            if _custom_type(parameter.type):
                proof = prove_parameter_materialization((parameter,), contract)
                if proof:
                    evidence = proof[0]
                    provenance = "type-materialization:" + "|".join(evidence.provenance)
                    detail = (
                        f"source-backed recursive materialization succeeded for {parameter.name or parameter.type}; "
                        f"expression={evidence.expression}"
                    )
                else:
                    provenance = None
                    detail = f"custom parameter type {parameter.type} still requires source-backed materialization"
                add(
                    Capability.TYPE_MATERIALIZATION,
                    parameter.name or parameter.type,
                    'target parameter model',
                    detail,
                    _type_subcapability(parameter.type),
                    provenance,
                )
    attacker = hypothesis.attacker_capability.lower()
    if re.search(r'callback|reentr', attacker):
        add(Capability.CALLBACK_HARNESS, 'attacker capability', 'hypothesis')
    if 'reentr' in attacker:
        add(Capability.REENTRANCY_HARNESS, 'attacker capability', 'hypothesis')
    if re.search(r'\bvalue\b|ether|native', attacker):
        add(Capability.VALUE_PROVISION, 'attacker capability', 'hypothesis')
    if re.search(r'token|erc20', attacker):
        add(Capability.TOKEN_PROVISION, 'attacker capability', 'hypothesis')
    unique = {}
    for item in requirements:
        unique[(item.capability, item.subject, item.source, item.subcapability)] = item
    return ExperimentContract(experiment.experiment_id, hypothesis.hypothesis_id, target_function, tuple(unique.values()))

def solve_capabilities(contract: ExperimentContract, availability: tuple[CapabilityAvailability, ...] | None = None) -> CapabilityResolution:
    available = availability or default_capability_availability()
    by_capability = {item.capability: item for item in available}
    gaps: list[CapabilityGap] = []
    for requirement in contract.requirements:
        item = by_capability.get(requirement.capability)
        if item is None:
            gaps.append(CapabilityGap(requirement.capability, requirement.subject, requirement.subcapability, CapabilityStatus.MISSING, 'capability is not registered'))
            continue
        if item.status == CapabilityStatus.AVAILABLE:
            continue
        if requirement.capability == Capability.TYPE_MATERIALIZATION and requirement.provenance:
            continue
        if item.status == CapabilityStatus.PARTIAL:
            if requirement.subcapability and requirement.subcapability not in item.subcapabilities:
                gaps.append(CapabilityGap(requirement.capability, requirement.subject, requirement.subcapability, CapabilityStatus.BLOCKED, f'partial capability lacks sub-capability {requirement.subcapability}'))
            else:
                gaps.append(CapabilityGap(requirement.capability, requirement.subject, requirement.subcapability, CapabilityStatus.PARTIAL, item.detail or 'target-specific materialization/readiness evidence is required', MaterializationStage.PREREQUISITES, 'capability', requirement.provenance))
            continue
        gaps.append(CapabilityGap(requirement.capability, requirement.subject, requirement.subcapability, item.status, item.detail or f'capability registry reports {item.status.value}'))
    return CapabilityResolution(contract, available, tuple(gaps))

def capability_clusters(resolutions: tuple[CapabilityResolution, ...]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for resolution in resolutions:
        for gap in resolution.gaps:
            if gap.status in {CapabilityStatus.MISSING, CapabilityStatus.BLOCKED, CapabilityStatus.PARTIAL}:
                key = gap.capability.value if gap.subcapability is None else f'{gap.capability.value}:{gap.subcapability}'
                counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))
