from cydra.capability_repair import (
    RepairResult,
    derive_repair_plan,
    build_repair_artifact,
    run_repair_loop,
)


def _campaign():
    return {
        "capability_clusters": [
            {
                "capability": "CALL_SEQUENCE",
                "count": 2,
                "hypothesis_ids": ["H-1", "H-2"],
                "experiment_ids": ["X-1", "X-2"],
                "stages": ["call_sequence"],
                "reasons": ["generic renderer failed"],
            },
            {
                "capability": "STATE_OBSERVATION:public_state_observation",
                "count": 1,
                "hypothesis_ids": ["H-3"],
                "experiment_ids": ["X-3"],
                "stages": ["observations"],
                "reasons": ["no deterministic observation"],
            },
        ]
    }


def test_repair_plan_clusters_by_generic_capability():
    plan = derive_repair_plan(_campaign())
    assert [item.key for item in plan.requirements] == [
        "CALL_SEQUENCE",
        "STATE_OBSERVATION:public_state_observation",
    ]
    assert plan.requirements[0].affected_hypothesis_ids == ("H-1", "H-2")
    assert plan.requirements[0].repair_scope == "generic_execution"


def test_repair_artifact_is_target_agnostic():
    artifact = build_repair_artifact(_campaign())
    assert artifact["mode"] == "generic_capability_repair"
    assert "H-1" in artifact["requirements"][0]["affected_hypothesis_ids"]
    encoded = str(artifact)
    assert "Hinkal" not in encoded
    assert "runAction" not in encoded


def test_repair_loop_requires_real_regression_before_rerun():
    calls = []

    def repair(requirement):
        calls.append(requirement.key)
        return RepairResult(
            key=requirement.key,
            applied=True,
            changed=True,
            regression_passed=True,
            message="generic repair applied and regression passed",
            implementation_id="generic:test",
        )

    campaign = run_repair_loop(_campaign(), repair=repair)
    assert campaign.stopped_reason == "repair_plan_exhausted"
    assert campaign.repaired_keys == (
        "CALL_SEQUENCE",
        "STATE_OBSERVATION:public_state_observation",
    )
    assert calls == [
        "CALL_SEQUENCE",
        "STATE_OBSERVATION:public_state_observation",
    ]


def test_repair_loop_stops_fail_closed_when_repair_is_not_verified():
    calls = []

    def repair(requirement):
        calls.append(requirement.key)
        return RepairResult(
            key=requirement.key,
            applied=True,
            changed=True,
            regression_passed=False,
            message="regression failed",
        )

    campaign = run_repair_loop(_campaign(), repair=repair)
    assert campaign.stopped_reason == "repair_blocked"
    assert campaign.repaired_keys == ()
    assert calls == ["CALL_SEQUENCE"]



def test_automatic_repair_plan_resolves_generic_provider():
    from cydra.capability_repair import build_automatic_repair_plan
    plan = build_automatic_repair_plan(_campaign())
    assert plan["fail_closed"] is False
    assert plan["requirements"][0]["status"] == "IMPLEMENTED"
    assert plan["requirements"][0]["provider"] == "sequence_foundry.call_sequence"


def test_automatic_repair_controller_regresses_then_replays_same_requirement():
    from cydra.capability_repair import run_automatic_repair_controller
    regressions = []
    replays = []

    def regression(provider):
        regressions.append(provider.implementation_id)
        return True

    def replay(requirement):
        replays.append(requirement.key)
        return {"same_experiment": requirement.affected_experiment_ids[0]}

    result = run_automatic_repair_controller(
        _campaign(), regression=regression, rerun_target=replay
    )
    assert result["status"] == "complete"
    assert regressions == [
        "sequence_foundry.call_sequence",
        "runtime_observation.state_observation",
    ]
    assert replays == [
        "CALL_SEQUENCE",
        "STATE_OBSERVATION:public_state_observation",
    ]


def test_automatic_repair_controller_fails_closed_for_unknown_capability():
    from cydra.capability_repair import run_automatic_repair_controller

    campaign = {
        "capability_clusters": [{
            "capability": "CRYPTOGRAPHIC_WITNESS",
            "hypothesis_ids": ["H-CRYPTO"],
            "experiment_ids": ["X-CRYPTO"],
            "stages": ["prerequisites"],
            "reasons": ["witness materialization is unresolved"],
        }]
    }
    result = run_automatic_repair_controller(
        campaign, regression=lambda _provider: True,
        rerun_target=lambda _requirement: {"unexpected": True},
    )
    assert result["status"] == "implementation_boundary"
    assert result["attempts"][0]["status"] == "UNIMPLEMENTED"
    assert result["attempts"][0]["rerun_requested"] is False
