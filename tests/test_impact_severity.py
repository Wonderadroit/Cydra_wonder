from cydra.finding import Finding
from cydra.impact import (
    AttackerAccess,
    Exploitability,
    ImpactAssessment,
    ImpactLevel,
    ImpactScope,
    Recoverability,
    Repeatability,
)


def assessed(level=ImpactLevel.HIGH):
    return ImpactAssessment(
        level,
        "protocol assets",
        "attacker can cause a demonstrated unauthorized asset transition",
        ("attacker reaches the vulnerable transition",),
        ("evidence:impact",),
        ImpactScope.PROTOCOL_WIDE,
        AttackerAccess.PERMISSIONLESS,
        Exploitability.DEMONSTRATED,
        Repeatability.REPEATABLE,
        Recoverability.IRREVERSIBLE,
    )


def test_impact_assessment_requires_structured_evidence_dimensions():
    impact = assessed()
    assert impact.assessed
    assert impact.severity is ImpactLevel.HIGH
    assert impact.as_dict()["exploitability"] == "demonstrated"


def test_unknown_or_incomplete_impact_is_not_assessed():
    impact = ImpactAssessment(
        ImpactLevel.UNKNOWN,
        "protocol assets",
        "something bad",
        evidence_ids=("evidence:impact",),
    )
    assert not impact.assessed


def test_finding_severity_is_bound_to_impact_level():
    finding = Finding(
        "finding:severity",
        "Verified impact",
        "Demonstrated consequence",
        "HIGH",
        assessed(ImpactLevel.HIGH),
        ("contract:Vault",),
        ("evidence:impact",),
        "hypothesis:h1",
        causal_chain_id="causal:c1",
    )
    assert finding.as_report_data()["severity"] == "HIGH"


def test_finding_rejects_severity_mismatch():
    try:
        Finding(
            "finding:mismatch",
            "Mismatch",
            "Demonstrated consequence",
            "CRITICAL",
            assessed(ImpactLevel.HIGH),
            ("contract:Vault",),
            ("evidence:impact",),
            "hypothesis:h1",
            causal_chain_id="causal:c1",
        )
    except ValueError as exc:
        assert "must match evidence-backed impact level" in str(exc)
    else:
        raise AssertionError("severity mismatch must be rejected")
