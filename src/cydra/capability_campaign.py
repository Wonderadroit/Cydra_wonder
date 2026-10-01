from __future__ import annotations

"""Generic batch capability-campaign aggregation.

This layer does not decide whether a target is vulnerable. It records every
failure that is observable in the current execution frontier, clusters shared
capability failures, and makes causal blocking explicit so later capability
fixes can be rerun systematically.
"""

from collections import defaultdict
from typing import Any


TERMINAL_STATUSES = {
    "EXECUTED",
    "CONFIRMED",
    "REJECTED",
    "UNMEASURABLE",
    "BLOCKED_BY_CAPABILITY",
    "NOT_REACHED",
    "CAPABILITY_FAILURE",
}


def _json(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        from dataclasses import asdict
        return {key: _json(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(k): _json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(v) for v in value]
    return value


def _resolution_mapping(resolution: Any) -> dict[str, Any]:
    """Normalize capability-resolution dataclasses and persisted mappings."""
    if resolution is None:
        return {}
    if isinstance(resolution, dict):
        return resolution
    if hasattr(resolution, "gaps"):
        return {"gaps": getattr(resolution, "gaps", ())}
    return {}


def _gap_key(gap: Any) -> str:
    if isinstance(gap, dict):
        capability = gap.get("capability", "UNKNOWN")
        sub = gap.get("subcapability")
    else:
        capability = getattr(gap, "capability", "UNKNOWN")
        sub = getattr(gap, "subcapability", None)
    capability = getattr(capability, "value", capability)
    return str(capability) if not sub else f"{capability}:{sub}"


def _status_kind(status: dict[str, Any]) -> str:
    if status.get("blind_executed"):
        classification = str(status.get("classification", "")).lower()
        if classification == "confirmed":
            return "CONFIRMED"
        if classification in {"rejected", "not_confirmed"}:
            return "REJECTED"
        if classification == "unmeasurable":
            return "UNMEASURABLE"
        return "EXECUTED"
    if status.get("capability_failure") or status.get("materialization_failure"):
        return "CAPABILITY_FAILURE"
    if status.get("classification_blocked_reason") or status.get("blocked_reason"):
        return "BLOCKED_BY_CAPABILITY"
    return "NOT_REACHED"


def build_capability_campaign(
    statuses: list[dict[str, Any]],
    execution_readiness: list[dict[str, Any]],
    planned_unimplemented: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a durable campaign ledger from all independently attempted work."""
    failures: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    planned_unimplemented = list(planned_unimplemented or [])
    clusters: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, str]] = []
    readiness_by_hypothesis = {
        item.get("hypothesis_id"): item for item in execution_readiness
    }

    for status in statuses:
        hypothesis_id = status.get("hypothesis_id")
        experiment_id = status.get("experiment_id") or (
            readiness_by_hypothesis.get(hypothesis_id, {}).get("capability_contract", {}) or {}
        ).get("experiment_id")
        kind = _status_kind(status)
        status["campaign_status"] = kind

        resolution = _resolution_mapping(status.get("capability_resolution"))
        gaps = list(resolution.get("gaps") or [])
        materialization = status.get("materialization_failure")
        if materialization:
            gap = materialization.get("gap") if isinstance(materialization, dict) else None
            if gap:
                gaps.append(gap)

        if kind in {"CAPABILITY_FAILURE", "BLOCKED_BY_CAPABILITY"}:
            record = {
                "hypothesis_id": hypothesis_id,
                "experiment_id": experiment_id,
                "class": status.get("class"),
                "target_function": status.get("target_function"),
                "stage": (
                    (materialization or {}).get("gap", {}).get("stage")
                    if isinstance(materialization, dict)
                    else None
                ) or "execution",
                "status": kind,
                "reason": status.get("blocked_reason")
                or status.get("classification_blocked_reason")
                or status.get("foundry_generation_blocked_reason"),
                "gaps": _json(gaps),
            }
            failures.append(record)

            if kind == "BLOCKED_BY_CAPABILITY":
                blocked.append({
                    "hypothesis_id": hypothesis_id,
                    "experiment_id": experiment_id,
                    "class": status.get("class"),
                    "target_function": status.get("target_function"),
                    "reason": record["reason"],
                    "required_capabilities": [
                        _gap_key(gap) for gap in gaps
                    ],
                })

        for gap in gaps:
            key = _gap_key(gap)
            cluster = clusters.setdefault(key, {
                "capability": key,
                "count": 0,
                "hypothesis_ids": [],
                "experiment_ids": [],
                "stages": [],
                "reasons": [],
            })
            cluster["count"] += 1
            if hypothesis_id and hypothesis_id not in cluster["hypothesis_ids"]:
                cluster["hypothesis_ids"].append(hypothesis_id)
            if experiment_id and experiment_id not in cluster["experiment_ids"]:
                cluster["experiment_ids"].append(experiment_id)
            stage = getattr(gap, "stage", None)
            if stage is None and isinstance(gap, dict):
                stage = gap.get("stage")
            stage = getattr(stage, "value", stage)
            if stage and stage not in cluster["stages"]:
                cluster["stages"].append(stage)
            reason = getattr(gap, "reason", None)
            if reason is None and isinstance(gap, dict):
                reason = gap.get("reason")
            if reason and reason not in cluster["reasons"]:
                cluster["reasons"].append(reason)
            if hypothesis_id:
                edges.append({"from": key, "to": hypothesis_id, "type": "blocks"})

    for item in readiness_by_hypothesis.values():
        resolution = _resolution_mapping(item.get("capability_resolution"))
        if not resolution:
            continue
        for gap in resolution.get("gaps", ()):
            key = _gap_key(gap)
            hypothesis_id = item.get("hypothesis_id")
            if hypothesis_id:
                edges.append({"from": key, "to": hypothesis_id, "type": "requires"})

    unique_edges = []
    seen_edges = set()
    for edge in edges:
        marker = tuple(edge.items())
        if marker not in seen_edges:
            seen_edges.add(marker)
            unique_edges.append(edge)

    counts = defaultdict(int)
    for status in statuses:
        counts[_status_kind(status)] += 1

    return {
        "schema_version": 1,
        "mode": "batch_capability_campaign",
        "status_taxonomy": sorted(TERMINAL_STATUSES),
        "summary": {
            "total_attempts": len(statuses),
            "by_status": dict(sorted(counts.items())),
            "capability_clusters": len(clusters),
            "blocked_experiments": len(blocked),
        },
        "capability_failures": failures,
        "blocked_experiments": blocked,
        "planned_unimplemented": planned_unimplemented,
        "capability_clusters": sorted(
            clusters.values(), key=lambda item: (-item["count"], item["capability"])
        ),
        "dependency_graph": {
            "nodes": sorted(
                set(clusters) | {
                    status.get("hypothesis_id")
                    for status in statuses
                    if status.get("hypothesis_id")
                } - {None}
            ),
            "edges": unique_edges,
        },
    }


def merge_campaigns(campaigns: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge per-source ledgers into one target-level campaign without deduping evidence away."""
    failures = []
    blocked = []
    planned_unimplemented = []
    clusters: dict[str, dict[str, Any]] = {}
    edges = []
    by_status = defaultdict(int)
    total_attempts = 0

    for campaign in campaigns:
        summary = campaign.get("summary", {})
        total_attempts += int(summary.get("total_attempts", 0))
        for key, value in (summary.get("by_status") or {}).items():
            by_status[key] += int(value)
        failures.extend(campaign.get("capability_failures", []))
        blocked.extend(campaign.get("blocked_experiments", []))
        planned_unimplemented.extend(campaign.get("planned_unimplemented", []))
        edges.extend(campaign.get("dependency_graph", {}).get("edges", []))
        for item in campaign.get("capability_clusters", []):
            key = item["capability"]
            target = clusters.setdefault(key, {
                "capability": key,
                "count": 0,
                "hypothesis_ids": [],
                "experiment_ids": [],
                "stages": [],
                "reasons": [],
            })
            target["count"] += int(item.get("count", 0))
            for field in ("hypothesis_ids", "experiment_ids", "stages", "reasons"):
                for value in item.get(field, []):
                    if value not in target[field]:
                        target[field].append(value)

    unique_edges = []
    seen = set()
    for edge in edges:
        marker = (edge.get("from"), edge.get("to"), edge.get("type"))
        if marker not in seen:
            seen.add(marker)
            unique_edges.append(edge)

    return {
        "schema_version": 1,
        "mode": "batch_capability_campaign",
        "summary": {
            "sources": len(campaigns),
            "total_attempts": total_attempts,
            "by_status": dict(sorted(by_status.items())),
            "capability_clusters": len(clusters),
            "blocked_experiments": len(blocked),
        },
        "capability_failures": failures,
        "blocked_experiments": blocked,
        "planned_unimplemented": planned_unimplemented,
        "capability_clusters": sorted(
            clusters.values(), key=lambda item: (-item["count"], item["capability"])
        ),
        "dependency_graph": {
            "nodes": sorted(
                {item["capability"] for item in clusters.values()}
                | {edge["to"] for edge in unique_edges if edge.get("to")}
            ),
            "edges": unique_edges,
        },
    }
