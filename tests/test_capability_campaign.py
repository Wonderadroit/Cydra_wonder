from cydra.capability_campaign import build_capability_campaign, merge_campaigns


def test_batch_campaign_clusters_shared_capability_and_blocks_experiments():
    statuses = [
        {
            "hypothesis_id": "H1",
            "experiment_id": "X1",
            "class": "state",
            "target_function": "a",
            "blind_executed": False,
            "classification": "NOT_REACHED",
            "classification_blocked_reason": "structured binding unavailable",
            "capability_resolution": {
                "gaps": [{
                    "capability": "TYPE_MATERIALIZATION",
                    "subcapability": "nested_custom_struct",
                    "stage": "prerequisites",
                    "reason": "nested struct cannot be materialized",
                }]
            },
        },
        {
            "hypothesis_id": "H2",
            "experiment_id": "X2",
            "class": "state",
            "target_function": "b",
            "blind_executed": False,
            "classification": "NOT_REACHED",
            "classification_blocked_reason": "structured binding unavailable",
            "capability_resolution": {
                "gaps": [{
                    "capability": "TYPE_MATERIALIZATION",
                    "subcapability": "nested_custom_struct",
                    "stage": "prerequisites",
                    "reason": "nested struct cannot be materialized",
                }]
            },
        },
        {
            "hypothesis_id": "H3",
            "experiment_id": "X3",
            "class": "authorization",
            "blind_executed": True,
            "classification": "rejected",
            "capability_resolution": {"gaps": []},
        },
    ]
    campaign = build_capability_campaign(statuses, [])
    cluster = campaign["capability_clusters"][0]

    assert cluster["capability"] == "TYPE_MATERIALIZATION:nested_custom_struct"
    assert cluster["count"] == 2
    assert campaign["summary"]["blocked_experiments"] == 2
    assert {item["hypothesis_id"] for item in campaign["blocked_experiments"]} == {"H1", "H2"}
    assert len(campaign["dependency_graph"]["edges"]) >= 2


def test_merge_campaigns_preserves_cluster_counts():
    merged = merge_campaigns([
        {
            "summary": {"total_attempts": 2, "by_status": {"BLOCKED_BY_CAPABILITY": 2}},
            "capability_failures": [],
            "blocked_experiments": [],
            "capability_clusters": [{
                "capability": "CALLER_CONSTRUCTION",
                "count": 2,
                "hypothesis_ids": ["H1", "H2"],
                "experiment_ids": ["X1", "X2"],
                "stages": ["prerequisites"],
                "reasons": ["caller missing"],
            }],
            "dependency_graph": {"edges": [{"from": "CALLER_CONSTRUCTION", "to": "H1", "type": "blocks"}]},
        }
    ])
    assert merged["summary"]["total_attempts"] == 2
    assert merged["capability_clusters"][0]["capability"] == "CALLER_CONSTRUCTION"
    assert merged["capability_clusters"][0]["count"] == 2


from cydra.execution_capabilities import (Capability, CapabilityAvailability, CapabilityGap, CapabilityResolution, CapabilityStatus, ExperimentContract)


def test_batch_campaign_accepts_capability_resolution_dataclass():
    resolution = CapabilityResolution(
        contract=ExperimentContract("X4", "H4", "target"),
        availability=(CapabilityAvailability(Capability.STATE_SETUP, CapabilityStatus.AVAILABLE, "test"),),
        gaps=(CapabilityGap(Capability.STATE_SETUP, "target", "mapping", CapabilityStatus.BLOCKED, "mapping setup unavailable"),),
    )
    statuses = [{
        "hypothesis_id": "H4",
        "experiment_id": "X4",
        "class": "state",
        "target_function": "target",
        "blind_executed": False,
        "classification_blocked_reason": "mapping setup unavailable",
        "capability_resolution": resolution,
    }]
    campaign = build_capability_campaign(statuses, [])
    assert campaign["summary"]["blocked_experiments"] == 1
    assert campaign["capability_clusters"][0]["capability"] == "STATE_SETUP:mapping"
