from __future__ import annotations
from dataclasses import dataclass
from enum import Enum


class ImpactLevel(str, Enum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


class ImpactScope(str, Enum):
    SINGLE_USER = "single_user"
    LIMITED = "limited"
    PROTOCOL_WIDE = "protocol_wide"
    SYSTEM_WIDE = "system_wide"
    UNKNOWN = "unknown"


class AttackerAccess(str, Enum):
    NONE = "none"
    PERMISSIONLESS = "permissionless"
    USER = "user"
    PRIVILEGED = "privileged"
    UNKNOWN = "unknown"


class Exploitability(str, Enum):
    DEMONSTRATED = "demonstrated"
    CONDITIONAL = "conditional"
    THEORETICAL = "theoretical"
    UNKNOWN = "unknown"


class Repeatability(str, Enum):
    REPEATABLE = "repeatable"
    ONE_SHOT = "one_shot"
    UNKNOWN = "unknown"


class Recoverability(str, Enum):
    RECOVERABLE = "recoverable"
    MANUAL = "manual"
    IRREVERSIBLE = "irreversible"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ImpactAssessment:
    level: ImpactLevel
    asset_at_risk: str
    consequence: str
    prerequisites: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    scope: ImpactScope = ImpactScope.UNKNOWN
    attacker_access: AttackerAccess = AttackerAccess.UNKNOWN
    exploitability: Exploitability = Exploitability.UNKNOWN
    repeatability: Repeatability = Repeatability.UNKNOWN
    recoverability: Recoverability = Recoverability.UNKNOWN

    @property
    def assessed(self) -> bool:
        return (
            self.level is not ImpactLevel.UNKNOWN
            and bool(self.asset_at_risk.strip())
            and bool(self.consequence.strip())
            and bool(self.evidence_ids)
            and self.scope is not ImpactScope.UNKNOWN
            and self.attacker_access is not AttackerAccess.UNKNOWN
            and self.exploitability is not Exploitability.UNKNOWN
            and self.repeatability is not Repeatability.UNKNOWN
            and self.recoverability is not Recoverability.UNKNOWN
        )

    @property
    def severity(self) -> ImpactLevel:
        return self.level

    def as_dict(self) -> dict:
        return {
            "level": self.level.value,
            "asset_at_risk": self.asset_at_risk,
            "consequence": self.consequence,
            "prerequisites": list(self.prerequisites),
            "evidence_ids": list(self.evidence_ids),
            "scope": self.scope.value,
            "attacker_access": self.attacker_access.value,
            "exploitability": self.exploitability.value,
            "repeatability": self.repeatability.value,
            "recoverability": self.recoverability.value,
        }
