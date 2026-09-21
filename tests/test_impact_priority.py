from cydra.impact import ImpactLevel
from cydra.impact_priority import FindingCollection, ImpactPriority, priority_for_potential


class F:
    def __init__(self, fid, level):
        self.finding_id = fid
        self.impact = type("I", (), {"level": level})()


def test_target_can_hold_multiple_findings():
    c = FindingCollection("target")
    c = c.add(F("f1", ImpactLevel.HIGH))
    c = c.add(F("f2", ImpactLevel.CRITICAL))
    assert len(c.findings) == 2
    assert [f.finding_id for f in c.ordered_by_severity()] == ["f2", "f1"]


def test_duplicate_finding_is_rejected():
    c = FindingCollection("target").add(F("f1", ImpactLevel.MEDIUM))
    try:
        c.add(F("f1", ImpactLevel.HIGH))
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate finding ID must be rejected")


def test_potential_priority_is_not_a_severity_verdict():
    assert priority_for_potential(ImpactPriority.CRITICAL) > priority_for_potential(ImpactPriority.LOW)
    assert priority_for_potential(ImpactPriority.UNKNOWN) == 1.0
