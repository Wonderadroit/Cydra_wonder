from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .impact import (
    AttackerAccess,
    Exploitability,
    ImpactAssessment,
    ImpactLevel,
    ImpactScope,
    Recoverability,
)


class ImpactKind(str, Enum):
    ASSET_LOSS = "asset_loss"
    ASSET_LOCK = "asset_lock"
    PROTOCOL_INTEGRITY = "protocol_integrity"
    ACCESS_CONTROL = "access_control"
    AVAILABILITY = "availability"
    DATA_DISCLOSURE = "data_disclosure"
    NONE = "none"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SeverityAssessment:
    level: ImpactLevel
    rationale: str
    evidence_ids: tuple[str, ...]
    determined: bool

    @property
    def usable(self) -> bool:
        return self.determined and self.level is not ImpactLevel.UNKNOWN and bool(self.evidence_ids)


def assess_severity(impact: ImpactAssessment, kind: ImpactKind) -> SeverityAssessment:
    """Conservatively classify demonstrated impact.

    This is a canonical baseline, not a claim that every bounty program uses
    the same thresholds. UNKNOWN is returned whenever the demonstrated facts
    do not support an unambiguous baseline classification.
    """
    evidence = impact.evidence_ids
    if (
        impact.level is ImpactLevel.UNKNOWN
        or not evidence
        or impact.exploitability is not Exploitability.DEMONSTRATED
        or impact.attacker_access is AttackerAccess.UNKNOWN
        or impact.scope is ImpactScope.UNKNOWN
        or impact.recoverability is Recoverability.UNKNOWN
    ):
        return SeverityAssessment(
            ImpactLevel.UNKNOWN,
            "insufficient demonstrated impact dimensions for a conservative severity classification",
            evidence,
            False,
        )

    broad = impact.scope in {ImpactScope.PROTOCOL_WIDE, ImpactScope.SYSTEM_WIDE}
    permissionless = impact.attacker_access is AttackerAccess.PERMISSIONLESS
    irreversible = impact.recoverability is Recoverability.IRREVERSIBLE

    if kind in {ImpactKind.ASSET_LOSS, ImpactKind.ASSET_LOCK}:
        if impact.scope is ImpactScope.SINGLE_USER:
            return SeverityAssessment(
                ImpactLevel.MEDIUM,
                "demonstrated asset impact is bounded to a single-user scope",
                evidence,
                True,
            )
        if broad and permissionless and irreversible:
            return SeverityAssessment(
                ImpactLevel.CRITICAL,
                "demonstrated permissionless irreversible asset impact spans a broad protocol/system scope",
                evidence,
                True,
            )
        if permissionless:
            return SeverityAssessment(
                ImpactLevel.HIGH,
                "demonstrated permissionless asset impact is exploitable but does not meet the conservative critical threshold",
                evidence,
                True,
            )
        return SeverityAssessment(
            ImpactLevel.HIGH,
            "demonstrated asset impact is material but requires a non-permissionless attacker capability",
            evidence,
            True,
        )

    if kind in {ImpactKind.ACCESS_CONTROL, ImpactKind.PROTOCOL_INTEGRITY}:
        if broad and permissionless:
            return SeverityAssessment(
                ImpactLevel.HIGH,
                "demonstrated permissionless control/integrity impact spans a broad protocol/system scope",
                evidence,
                True,
            )
        return SeverityAssessment(
            ImpactLevel.MEDIUM,
            "demonstrated control/integrity impact is narrower or requires additional access",
            evidence,
            True,
        )

    if kind is ImpactKind.AVAILABILITY:
        return SeverityAssessment(
            ImpactLevel.MEDIUM if broad else ImpactLevel.LOW,
            "demonstrated availability impact classified by affected scope",
            evidence,
            True,
        )

    if kind is ImpactKind.DATA_DISCLOSURE:
        return SeverityAssessment(
            ImpactLevel.MEDIUM if broad else ImpactLevel.LOW,
            "demonstrated disclosure impact classified by affected scope",
            evidence,
            True,
        )

    if kind is ImpactKind.NONE:
        return SeverityAssessment(ImpactLevel.NONE, "no material security consequence was demonstrated", evidence, True)

    return SeverityAssessment(
        ImpactLevel.UNKNOWN,
        "impact kind is unresolved; severity cannot be safely inferred",
        evidence,
        False,
    )
