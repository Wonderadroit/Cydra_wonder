from cydra.impact import (
    AttackerAccess,
    Exploitability,
    ImpactAssessment,
    ImpactLevel,
    ImpactScope,
    Recoverability,
    Repeatability,
)
from cydra.severity import ImpactKind, SeverityPolicy, apply_severity_policy, assess_severity


def impact(scope, access, recoverability):
    return ImpactAssessment(
        ImpactLevel.HIGH,
        "protocol assets",
        "demonstrated unauthorized asset transition",
        (),
        ("e1",),
        scope,
        access,
        Exploitability.DEMONSTRATED,
        Repeatability.REPEATABLE,
        recoverability,
    )


def test_permissionless_irreversible_broad_asset_loss_is_critical():
    result = assess_severity(
        impact(ImpactScope.PROTOCOL_WIDE, AttackerAccess.PERMISSIONLESS, Recoverability.IRREVERSIBLE),
        ImpactKind.ASSET_LOSS,
    )
    assert result.level is ImpactLevel.CRITICAL
    assert result.usable


def test_permissionless_bounded_asset_loss_is_high():
    result = assess_severity(
        impact(ImpactScope.LIMITED, AttackerAccess.PERMISSIONLESS, Recoverability.RECOVERABLE),
        ImpactKind.ASSET_LOSS,
    )
    assert result.level is ImpactLevel.HIGH


def test_single_user_asset_loss_is_medium():
    result = assess_severity(
        impact(ImpactScope.SINGLE_USER, AttackerAccess.PERMISSIONLESS, Recoverability.RECOVERABLE),
        ImpactKind.ASSET_LOSS,
    )
    assert result.level is ImpactLevel.MEDIUM


def test_unresolved_dimensions_are_unknown_not_guessed():
    result = assess_severity(
        ImpactAssessment(
            ImpactLevel.HIGH,
            "assets",
            "possible loss",
            evidence_ids=("e1",),
        ),
        ImpactKind.ASSET_LOSS,
    )
    assert result.level is ImpactLevel.UNKNOWN
    assert not result.determined


def test_program_policy_can_represent_a_different_allowed_taxonomy():
    assessment = assess_severity(
        impact(ImpactScope.PROTOCOL_WIDE, AttackerAccess.PERMISSIONLESS, Recoverability.IRREVERSIBLE),
        ImpactKind.ASSET_LOSS,
    )
    policy = SeverityPolicy(levels=(ImpactLevel.HIGH.value, ImpactLevel.MEDIUM.value, ImpactLevel.LOW.value, ImpactLevel.NONE.value))
    result = apply_severity_policy(assessment, policy)
    assert result.level is ImpactLevel.UNKNOWN
    assert not result.determined
