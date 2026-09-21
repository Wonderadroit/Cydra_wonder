from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from .impact import ImpactLevel


class ImpactPriority(IntEnum):
    """Research priority before confirmation; never a severity verdict."""

    UNKNOWN = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass(frozen=True)
class FindingCollection:
    """A target-scoped set of independently confirmed findings.

    Findings are keyed by finding_id. A target can therefore accumulate multiple
    findings without replacing an earlier confirmed issue.
    """

    target: str
    findings: tuple[object, ...] = ()

    def add(self, finding: object) -> "FindingCollection":
        finding_id = getattr(finding, "finding_id", "")
        if not finding_id:
            raise ValueError("finding must expose a non-empty finding_id")
        if any(getattr(item, "finding_id", None) == finding_id for item in self.findings):
            raise ValueError(f"finding already exists in target collection: {finding_id}")
        return FindingCollection(self.target, self.findings + (finding,))

    def ordered_by_severity(self) -> tuple[object, ...]:
        rank = {
            ImpactLevel.UNKNOWN.value: 0,
            ImpactLevel.NONE.value: 1,
            ImpactLevel.LOW.value: 2,
            ImpactLevel.MEDIUM.value: 3,
            ImpactLevel.HIGH.value: 4,
            ImpactLevel.CRITICAL.value: 5,
        }
        def severity_rank(finding: object) -> int:
            impact = getattr(finding, "impact", None)
            level = getattr(impact, "level", ImpactLevel.UNKNOWN)
            value = level.value if isinstance(level, ImpactLevel) else str(level)
            return rank.get(value, 0)
        return tuple(sorted(self.findings, key=severity_rank, reverse=True))


def priority_for_potential(level: ImpactPriority) -> float:
    """Convert explicit pre-confirmation impact potential to a selection weight.

    UNKNOWN has no bonus. This value is only a prioritization signal; confirmation
    and final severity remain evidence-backed.
    """
    return {ImpactPriority.UNKNOWN: 1.0, ImpactPriority.LOW: 1.0, ImpactPriority.MEDIUM: 1.25, ImpactPriority.HIGH: 1.5, ImpactPriority.CRITICAL: 1.75}[level]
