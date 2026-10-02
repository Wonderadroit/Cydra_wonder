from __future__ import annotations

"""Generic capability-repair planning and resumable campaign control."""

from dataclasses import dataclass
from typing import Callable, Mapping


@dataclass(frozen=True)
class RepairRequirement:
    key: str
    capability: str
    subcapability: str | None
    stage: str
    reason: str
    provenance: str | None
    affected_hypothesis_ids: tuple[str, ...] = ()
    affected_experiment_ids: tuple[str, ...] = ()
    repair_scope: str = "generic_execution"


@dataclass(frozen=True)
class RepairPlan:
    requirements: tuple[RepairRequirement, ...]
    generated_from: str = "capability_campaign"
    schema_version: int = 1

    @property
    def actionable(self) -> tuple[RepairRequirement, ...]:
        return tuple(item for item in self.requirements if item.repair_scope == "generic_execution")


@dataclass(frozen=True)
class RepairResult:
    key: str
    applied: bool
    changed: bool
    regression_passed: bool
    message: str
    implementation_id: str | None = None


@dataclass(frozen=True)
class RepairIteration:
    requirement: RepairRequirement
    repair: RepairResult
    rerun_requested: bool


@dataclass(frozen=True)
class RepairCampaign:
    plan: RepairPlan
    iterations: tuple[RepairIteration, ...] = ()
    rounds: int = 0
    stopped_reason: str = "no_requirements"

    @property
    def repaired_keys(self) -> tuple[str, ...]:
        return tuple(
            item.requirement.key
            for item in self.iterations
            if item.repair.applied and item.repair.regression_passed
        )


KNOWN_GENERIC_CAPABILITIES: Mapping[str, str] = {
    "CALL_SEQUENCE": "ordered-call materialization and renderer diagnostics",
    "CONSTRUCTOR_SETUP": "generic constructor argument materialization",
    "TYPE_MATERIALIZATION": "source-backed ABI/type materialization",
    "STATE_OBSERVATION": "bounded deterministic state observation",
    "CALLER_CONSTRUCTION": "target-derived caller/role construction",
    "STATE_SETUP": "target-derived constructible state setup",
    "INPUT_CONSTRUCTION": "source-backed execution predicate/input construction",
    "EXECUTION_CONTEXT": "deterministic runtime-context construction",
}


def derive_repair_plan(campaign: Mapping[str, object]) -> RepairPlan:
    """Cluster campaign gaps into reusable generic repair requirements."""
    clusters = campaign.get("capability_clusters") or ()
    requirements: list[RepairRequirement] = []

    for cluster in clusters:
        if not isinstance(cluster, Mapping):
            continue
        key = str(cluster.get("capability") or "UNKNOWN")
        capability, _, sub = key.partition(":")
        stages = tuple(str(item) for item in (cluster.get("stages") or ()) if item)
        reasons = tuple(str(item) for item in (cluster.get("reasons") or ()) if item)
        affected_h = tuple(str(item) for item in (cluster.get("hypothesis_ids") or ()) if item)
        affected_x = tuple(str(item) for item in (cluster.get("experiment_ids") or ()) if item)
        requirements.append(
            RepairRequirement(
                key=key,
                capability=capability,
                subcapability=sub or None,
                stage=stages[0] if stages else "execution",
                reason=reasons[0] if reasons else KNOWN_GENERIC_CAPABILITIES.get(
                    capability, "generic execution capability is missing"
                ),
                provenance=None,
                affected_hypothesis_ids=affected_h,
                affected_experiment_ids=affected_x,
            )
        )

    requirements.sort(key=lambda item: (item.key, item.stage, item.reason))
    return RepairPlan(tuple(requirements))


def build_repair_artifact(campaign: Mapping[str, object]) -> dict[str, object]:
    """Persist the machine-actionable repair contract beside campaign evidence."""
    plan = derive_repair_plan(campaign)
    return {
        "schema_version": plan.schema_version,
        "mode": "generic_capability_repair",
        "generated_from": plan.generated_from,
        "requirements": [
            {
                "key": item.key,
                "capability": item.capability,
                "subcapability": item.subcapability,
                "stage": item.stage,
                "reason": item.reason,
                "provenance": item.provenance,
                "affected_hypothesis_ids": list(item.affected_hypothesis_ids),
                "affected_experiment_ids": list(item.affected_experiment_ids),
                "repair_scope": item.repair_scope,
                "generic_contract": KNOWN_GENERIC_CAPABILITIES.get(
                    item.capability,
                    "implement the missing capability at the generic execution abstraction",
                ),
            }
            for item in plan.requirements
        ],
    }


def run_repair_loop(
    campaign: Mapping[str, object],
    *,
    repair: Callable[[RepairRequirement], RepairResult],
    max_rounds: int = 8,
) -> RepairCampaign:
    """Run a bounded repair/regression controller.

    The repair callback is the only mutation boundary. A successful repair is
    eligible for the caller's exact-target rerun; no security result is inferred.
    """
    plan = derive_repair_plan(campaign)
    iterations: list[RepairIteration] = []
    seen: set[str] = set()

    for requirement in plan.actionable:
        if len(iterations) >= max_rounds:
            return RepairCampaign(plan, tuple(iterations), len(iterations), "repair_budget_exhausted")
        if requirement.key in seen:
            continue
        seen.add(requirement.key)
        result = repair(requirement)
        rerun = bool(result.applied and result.changed and result.regression_passed)
        iterations.append(RepairIteration(requirement, result, rerun))
        if not rerun:
            return RepairCampaign(plan, tuple(iterations), len(iterations), "repair_blocked")

    if not iterations:
        return RepairCampaign(plan, (), 0, "no_requirements")
    return RepairCampaign(plan, tuple(iterations), len(iterations), "repair_plan_exhausted")



@dataclass(frozen=True)
class RepairProvider:
    """Generic implementation boundary for one capability/sub-capability."""
    capability: str
    subcapabilities: tuple[str, ...]
    implementation_id: str
    regression_command: tuple[str, ...]
    description: str


DEFAULT_REPAIR_PROVIDERS: tuple[RepairProvider, ...] = (
    RepairProvider("CALL_SEQUENCE", ("ordered_steps",), "sequence_foundry.call_sequence",
                   ("python", "-m", "pytest", "tests/test_sequence_foundry.py"),
                   "generic ordered-call experiment materialization"),
    RepairProvider("CONSTRUCTOR_SETUP", ("array", "primitive", "interface", "custom_struct"),
                   "sequence_foundry.constructor_materialization",
                   ("python", "-m", "pytest", "tests/test_sequence_foundry.py", "tests/test_execution_readiness.py"),
                   "generic constructor argument materialization"),
    RepairProvider("TYPE_MATERIALIZATION",
                   ("primitive", "array", "tuple", "custom_struct", "nested_custom_struct", "namespaced_custom_struct"),
                   "sequence_foundry.type_materialization",
                   ("python", "-m", "pytest", "tests/test_sequence_foundry.py"),
                   "source-backed recursive ABI/type materialization"),
    RepairProvider("CALLER_CONSTRUCTION", ("role", "predicate"), "execution_readiness.caller_construction",
                   ("python", "-m", "pytest", "tests/test_execution_readiness.py"),
                   "target-derived caller and role construction"),
    RepairProvider("ROLE_ESTABLISHMENT", ("role",), "execution_readiness.role_establishment",
                   ("python", "-m", "pytest", "tests/test_execution_readiness.py"),
                   "target-derived role establishment"),
    RepairProvider("STATE_SETUP", ("constructible",), "execution_readiness.state_setup",
                   ("python", "-m", "pytest", "tests/test_execution_readiness.py", "tests/test_prerequisite_graph.py"),
                   "target-derived constructible state setup"),
    RepairProvider("STATE_OBSERVATION",
                   ("public_scalar", "public_mapping", "state_relation"),
                   "runtime_observation.state_observation",
                   ("python", "-m", "pytest", "tests/test_runtime_observation.py", "tests/test_state_relation_observation.py"),
                   "bounded deterministic state observation"),
    RepairProvider("INTERNAL_CALL_PROPAGATION", ("producer", "dependency"),
                   "execution_readiness.internal_call_propagation",
                   ("python", "-m", "pytest", "tests/test_execution_readiness.py"),
                   "internal producer/dependency propagation"),
)


def repair_provider_for(
    requirement: RepairRequirement,
    providers: tuple[RepairProvider, ...] = DEFAULT_REPAIR_PROVIDERS,
) -> RepairProvider | None:
    """Select a generic implementation without target-specific matching."""
    for provider in providers:
        if provider.capability == requirement.capability and (
            requirement.subcapability is None
            or requirement.subcapability in provider.subcapabilities
        ):
            return provider
    return None


def build_automatic_repair_plan(
    campaign: Mapping[str, object],
    providers: tuple[RepairProvider, ...] = DEFAULT_REPAIR_PROVIDERS,
) -> dict[str, object]:
    """Turn the persisted repair contract into an executable engineering plan."""
    plan = derive_repair_plan(campaign)
    requirements = []
    for item in plan.requirements:
        provider = repair_provider_for(item, providers)
        requirements.append({
            "key": item.key,
            "capability": item.capability,
            "subcapability": item.subcapability,
            "stage": item.stage,
            "reason": item.reason,
            "affected_hypothesis_ids": list(item.affected_hypothesis_ids),
            "affected_experiment_ids": list(item.affected_experiment_ids),
            "provider": provider.implementation_id if provider else None,
            "regression_command": list(provider.regression_command) if provider else None,
            "status": "IMPLEMENTED" if provider else "UNIMPLEMENTED",
        })
    return {
        "schema_version": 1,
        "mode": "automatic_generic_repair",
        "requirements": requirements,
        "fail_closed": any(item["status"] == "UNIMPLEMENTED" for item in requirements),
    }


def run_automatic_repair_controller(
    campaign: Mapping[str, object],
    *,
    regression: Callable[[RepairProvider], bool],
    rerun_target: Callable[[RepairRequirement], Mapping[str, object]],
    providers: tuple[RepairProvider, ...] = DEFAULT_REPAIR_PROVIDERS,
    max_rounds: int = 8,
) -> dict[str, object]:
    """Regress each registered generic capability, replay the same target, then continue.

    No target code is changed and no security result is inferred. If no generic
    provider exists, the controller stops fail-closed at the implementation boundary.
    """
    plan = derive_repair_plan(campaign)
    attempts: list[dict[str, object]] = []
    seen: set[str] = set()

    for requirement in plan.actionable:
        if len(attempts) >= max_rounds:
            return {"schema_version": 1, "mode": "automatic_generic_repair",
                    "status": "repair_budget_exhausted", "attempts": attempts}
        if requirement.key in seen:
            continue
        seen.add(requirement.key)
        provider = repair_provider_for(requirement, providers)
        if provider is None:
            attempts.append({"requirement": requirement.key, "status": "UNIMPLEMENTED",
                             "message": "no registered generic implementation; fail-closed",
                             "rerun_requested": False})
            return {"schema_version": 1, "mode": "automatic_generic_repair",
                    "status": "implementation_boundary", "attempts": attempts}
        if not regression(provider):
            attempts.append({"requirement": requirement.key, "provider": provider.implementation_id,
                             "status": "REGRESSION_FAILED", "rerun_requested": False})
            return {"schema_version": 1, "mode": "automatic_generic_repair",
                    "status": "regression_failed", "attempts": attempts}
        replay = dict(rerun_target(requirement))
        attempts.append({"requirement": requirement.key, "provider": provider.implementation_id,
                         "status": "REPLAYED", "regression_passed": True,
                         "rerun_requested": True, "replay": replay})

    return {"schema_version": 1, "mode": "automatic_generic_repair",
            "status": "complete" if attempts else "no_requirements", "attempts": attempts}
