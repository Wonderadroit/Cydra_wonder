from __future__ import annotations
from dataclasses import dataclass
from .impact import ImpactAssessment

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

    def as_report_data(self) -> dict:
        return {
            "finding_id": self.finding_id, "title": self.title, "summary": self.summary,
            "severity": self.severity,
            "impact": {"level": self.impact.level.value, "asset_at_risk": self.impact.asset_at_risk,
                       "consequence": self.impact.consequence, "prerequisites": list(self.impact.prerequisites)},
            "affected_components": list(self.affected_components), "evidence_ids": list(self.evidence_ids),
            "hypothesis_id": self.hypothesis_id, "poc_reference": self.poc_reference,
            "causal_chain_id": self.causal_chain_id, "audit_session_id": self.audit_session_id,
        }
