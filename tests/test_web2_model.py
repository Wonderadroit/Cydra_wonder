from cydra.web2_model import (
    Web2EndpointModel,
    Web2IdentityModel,
    Web2ResourceModel,
    Web2TargetModel,
)


def build_model() -> Web2TargetModel:
    model = Web2TargetModel("https://authorized.example")
    model.add_identity(Web2IdentityModel("alice", "Alice"))
    model.add_identity(Web2IdentityModel("bob", "Bob"))
    model.add_resource(Web2ResourceModel("resource:1", "Alice record", owner_identity_id="alice", identifier="1"))
    model.add_endpoint(Web2EndpointModel("endpoint:get-record", "GET", "/records/{id}", ("resource:1",), "read"))
    return model


def test_model_records_explicit_ownership_and_builds_conservative_expectation():
    model = build_model()

    relations = model.infer_ownership_authorization()

    assert len(relations) == 1
    assert relations[0].identity_id == "alice"
    assert relations[0].resource_id == "resource:1"
    assert relations[0].expected == "allow_owner"


def test_cross_identity_pairs_are_planning_candidates_not_findings():
    model = build_model()

    assert model.candidate_cross_identity_pairs() == (
        ("alice", "bob", "resource:1"),
    )
    assert not model.observations


def test_model_rejects_unknown_resource_owner():
    model = Web2TargetModel("https://authorized.example")

    try:
        model.add_resource(Web2ResourceModel("resource:1", "record", owner_identity_id="missing"))
    except ValueError as error:
        assert "owner" in str(error)
    else:
        raise AssertionError("unknown owner should be rejected")
