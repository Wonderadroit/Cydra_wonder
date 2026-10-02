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
