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


# These providers correspond to generic execution abstractions already present in
# CYDRA's source-backed readiness model. Registering a provider means the generic
# capability can be exercised and regressed; it does not make an arbitrary target
# witness satisfiable.
GENERIC_EXECUTION_PREDICATE_PROVIDERS: tuple[RepairProvider, ...] = (
    RepairProvider(
        "LOCAL_EXECUTION",
        ("internal_execution_predicate", "execution_predicate"),
        "execution_readiness.local_execution_predicate",
        ("python", "-m", "pytest", "tests/test_execution_readiness.py"),
        "source-backed local binding and deterministic execution-predicate resolution",
    ),
    RepairProvider(
        "STATE_OBSERVATION",
        ("state_predicate", "public_state_observation", "public_scalar", "public_mapping", "state_relation"),
        "execution_readiness.state_observation",
        ("python", "-m", "pytest", "tests/test_execution_readiness.py", "tests/test_runtime_observation.py", "tests/test_state_relation_observation.py"),
        "source/compiler-backed state observation and prerequisite resolution",
    ),
    RepairProvider(
        "EXECUTION_READINESS",
        ("execution_value_runtime_dependency",),
        "execution_readiness.runtime_dependency_resolution",
        ("python", "-m", "pytest", "tests/test_execution_readiness.py"),
        "generic runtime-value dependency discovery and fail-closed readiness",
    ),
)

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
    RepairProvider("CALLER_CONSTRUCTION", ("role", "predicate", "caller_role"), "execution_readiness.caller_construction",
                   ("python", "-m", "pytest", "tests/test_execution_readiness.py"),
                   "target-derived caller and role construction"),
    RepairProvider("ROLE_ESTABLISHMENT", ("role",), "execution_readiness.role_establishment",
                   ("python", "-m", "pytest", "tests/test_execution_readiness.py"),
                   "target-derived role establishment"),
    RepairProvider("STATE_SETUP", ("constructible",), "execution_readiness.state_setup",
                   ("python", "-m", "pytest", "tests/test_execution_readiness.py", "tests/test_prerequisite_graph.py"),
                   "target-derived constructible state setup"),
    RepairProvider("STATE_OBSERVATION",
                   ("public_scalar", "public_mapping", "state_relation", "public_state_observation"),
                   "runtime_observation.state_observation",
                   ("python", "-m", "pytest", "tests/test_runtime_observation.py", "tests/test_state_relation_observation.py"),
                   "bounded deterministic state observation"),
    RepairProvider("INTERNAL_CALL_PROPAGATION", ("producer", "dependency"),
                   "execution_readiness.internal_call_propagation",
                   ("python", "-m", "pytest", "tests/test_execution_readiness.py"),
                   "internal producer/dependency propagation"),
    RepairProvider("INPUT_CONSTRUCTION", ("execution_predicate", "internal_execution_predicate", "abi", "scalar", "array"),
                   "experiment_inputs.source_backed_materialization",
                   ("python", "-m", "pytest", "tests/test_experiment_inputs.py", "tests/test_execution_capabilities.py"),
                   "source-backed execution input construction"),
    RepairProvider("EXECUTION_CONTEXT", ("runtime", "caller", "dependency", "execution_value_runtime_dependency"),
                   "execution_readiness.runtime_context",
                   ("python", "-m", "pytest", "tests/test_execution_readiness.py"),
                   "deterministic runtime-context construction"),
    *GENERIC_EXECUTION_PREDICATE_PROVIDERS,
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
    max_rounds: int | None = None,
) -> dict[str, object]:
    """Run the generic repair/replay frontier to semantic convergence.

    A replay may expose a new capability cluster. That cluster is merged into
    the frontier and processed in a later round. A repair is never considered
    successful merely because its regression passed: the frozen-target replay
    must complete and may expose additional prerequisites.
    """
    frontier = dict(campaign)
    attempts: list[dict[str, object]] = []
    seen: set[str] = set()
    boundaries: list[str] = []

    round_number = 0
    while max_rounds is None or round_number < max_rounds:
        round_number += 1
        plan = derive_repair_plan(frontier)
        actionable = [item for item in plan.actionable if item.key not in seen]
        if not actionable:
            status = "implementation_boundary" if boundaries else (
                "complete" if attempts else "no_requirements"
            )
            result = {
                "schema_version": 1,
                "mode": "automatic_generic_repair",
                "status": status,
                "rounds": round_number - 1,
                "attempts": attempts,
            }
            if boundaries:
                result["implementation_boundaries"] = boundaries
            return result

        progressed = False
        for requirement in actionable:
            seen.add(requirement.key)
            provider = repair_provider_for(requirement, providers)
            if provider is None:
                attempts.append({
                    "round": round_number,
                    "requirement": requirement.key,
                    "status": "UNIMPLEMENTED",
                    "message": "no registered generic implementation; fail-closed",
                    "rerun_requested": False,
                })
                boundaries.append(requirement.key)
                # One unknown capability must not prevent independent known
                # generic capabilities from being repaired and replayed.
                continue

            if not regression(provider):
                attempts.append({
                    "round": round_number,
                    "requirement": requirement.key,
                    "provider": provider.implementation_id,
                    "status": "REGRESSION_FAILED",
                    "rerun_requested": False,
                })
                return {
                    "schema_version": 1,
                    "mode": "automatic_generic_repair",
                    "status": "regression_failed",
                    "rounds": round_number,
                    "attempts": attempts,
                }

            replay = dict(rerun_target(requirement))
            attempt = {
                "round": round_number,
                "requirement": requirement.key,
                "provider": provider.implementation_id,
                "status": "REPLAYED",
                "regression_passed": True,
                "rerun_requested": True,
                "replay": replay,
            }
            attempts.append(attempt)
            progressed = True

            # The replay contract may return a newly observed capability
            # campaign. Merge it into the next frontier without trusting
            # free-form status text as evidence.
            next_campaign = replay.get("campaign")
            if isinstance(next_campaign, Mapping):
                # A provider is not a repair if the exact same capability remains
                # unresolved after replay. Preserve that boundary explicitly so
                # the controller cannot report "complete" merely because the
                # provider itself ran.
                replay_keys = {
                    str(cluster.get("capability"))
                    for cluster in (next_campaign.get("capability_clusters") or ())
                    if isinstance(cluster, Mapping) and cluster.get("capability")
                }
                if requirement.key in replay_keys:
                    boundary = f"replay_unresolved:{requirement.key}"
                    if boundary not in boundaries:
                        boundaries.append(boundary)
            if isinstance(next_campaign, Mapping):
                old_clusters = list(frontier.get("capability_clusters") or ())
                new_clusters = list(next_campaign.get("capability_clusters") or ())
                frontier["capability_clusters"] = old_clusters + [
                    cluster for cluster in new_clusters
                    if isinstance(cluster, Mapping)
                ]

        if not progressed:
            break

    if boundaries:
        return {
            "schema_version": 1,
            "mode": "automatic_generic_repair",
            "status": "implementation_boundary",
            "rounds": round_number,
            "attempts": attempts,
            "implementation_boundaries": boundaries,
        }

    return {
        "schema_version": 1,
        "mode": "automatic_generic_repair",
        "status": "repair_budget_exhausted",
        "rounds": max_rounds,
        "attempts": attempts,
    }
