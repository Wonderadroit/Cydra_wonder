from __future__ import annotations
from dataclasses import dataclass
from .impact import ImpactAssessment, ImpactLevel


@dataclass(frozen=True)
class Finding:
    finding_id: str
    title: str
    summary: str
    severity: str
    impact: ImpactAssessment
    affected_components: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    hypothesis_id: str
    poc_reference: str | None = None
    causal_chain_id: str | None = None
    audit_session_id: str | None = None

    def __post_init__(self) -> None:
        severity = self.severity.value if isinstance(self.severity, ImpactLevel) else self.severity
        if severity not in {level.value for level in ImpactLevel if level is not ImpactLevel.UNKNOWN}:
            raise ValueError(f"finding severity is not canonical: {severity}")
        if severity != self.impact.level.value:
            raise ValueError(
                f"finding severity must match evidence-backed impact level: "
                f"{severity} != {self.impact.level.value}"
            )
        if not self.impact.assessed:
            raise ValueError("finding requires a complete evidence-backed impact assessment")

    def as_report_data(self) -> dict:
        return {
            "finding_id": self.finding_id,
            "title": self.title,
            "summary": self.summary,
            "severity": self.impact.level.value,
            "impact": self.impact.as_dict(),
            "affected_components": list(self.affected_components),
            "evidence_ids": list(self.evidence_ids),
            "hypothesis_id": self.hypothesis_id,
            "poc_reference": self.poc_reference,
            "causal_chain_id": self.causal_chain_id,
            "audit_session_id": self.audit_session_id,
        }
