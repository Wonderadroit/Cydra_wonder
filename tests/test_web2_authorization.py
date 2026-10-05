from cydra.web2_authorization import plan_ownership_differential
from cydra.web2_model import Web2EndpointModel, Web2IdentityModel, Web2ResourceModel, Web2TargetModel


def test_planner_creates_differential_experiment_without_declaring_a_finding():
    model = Web2TargetModel("https://authorized.example")
    model.add_identity(Web2IdentityModel("alice", "Alice"))
    model.add_identity(Web2IdentityModel("bob", "Bob"))
    model.add_resource(Web2ResourceModel("resource:1", "Alice record", "alice", "1"))
    model.add_endpoint(Web2EndpointModel("endpoint:get", "GET", "/records/{id}", ("resource:1",), "read"))

    plan = plan_ownership_differential(
        model,
        owner_identity_id="alice",
        other_identity_id="bob",
        resource_id="resource:1",
        endpoint_id="endpoint:get",
    )

    assert plan.hypothesis.status == "proposed"
    assert plan.hypothesis.expected_impact == "UNAUTHORIZED_RESOURCE_ACCESS"
    assert len(plan.experiment.actions) == 2
    assert plan.experiment.actions[0].inputs["identity_id"] == "alice"
    assert plan.experiment.actions[1].inputs["identity_id"] == "bob"
    assert plan.experiment.actions[1].inputs["path"] == "/records/1"


def test_planner_requires_explicit_ownership():
    model = Web2TargetModel("https://authorized.example")
    model.add_identity(Web2IdentityModel("alice", "Alice"))
    model.add_identity(Web2IdentityModel("bob", "Bob"))
    model.add_resource(Web2ResourceModel("resource:1", "record", "alice", "1"))
    model.add_endpoint(Web2EndpointModel("endpoint:get", "GET", "/records/{id}", ("resource:1",), "read"))

    try:
        plan_ownership_differential(
            model,
            owner_identity_id="bob",
            other_identity_id="alice",
            resource_id="resource:1",
            endpoint_id="endpoint:get",
        )
    except ValueError as error:
        assert "ownership" in str(error)
    else:
        raise AssertionError("planner must reject an unsupported ownership claim")
