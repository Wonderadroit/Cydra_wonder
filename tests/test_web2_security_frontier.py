from cydra.hypotheses import Hypothesis
from cydra.web2_frontier import SecuritySurfaceKind, build_web2_security_frontier
from cydra.web2_model import Web2EndpointModel, Web2IdentityModel, Web2TargetModel
from cydra.web2_reasoning import select_next_web2_experiment


def model_with_reachable_surfaces():
    model = Web2TargetModel("https://authorized.example")
    model.add_identity(Web2IdentityModel("alice", "owner"))
    model.add_endpoint(Web2EndpointModel("public", "GET", "/public/items", action="list"))
    model.add_endpoint(Web2EndpointModel("admin", "POST", "/admin/action", action="admin_action"))
    model.add_observation(__import__("cydra.web2_model", fromlist=["Web2ObservationModel"]).Web2ObservationModel(
        "obs:public", "public", "alice", 200, "a" * 64, 10, "e:public"
    ))
    return model


def test_frontier_keeps_unrelated_reachable_surface_executable_when_resource_acquisition_is_blocked():
    model = model_with_reachable_surfaces()
    frontier = build_web2_security_frontier(model, blocked_capabilities=("RESOURCE_STATE_ACQUISITION",))
    assert frontier.executable
    assert any(item.endpoint_id == "public" and item.kind == SecuritySurfaceKind.OBSERVATION for item in frontier.executable)
    assert all(item.blocker != "RESOURCE_STATE_ACQUISITION" for item in frontier.executable)


def test_frontier_prioritizes_state_and_authorization_questions():
    model = model_with_reachable_surfaces()
    model.add_observation(__import__("cydra.web2_model", fromlist=["Web2ObservationModel"]).Web2ObservationModel(
        "obs:admin", "admin", "alice", 200, "b" * 64, 20, "e:admin"
    ))
    frontier = build_web2_security_frontier(model)
    assert frontier.executable[0].priority >= frontier.executable[-1].priority
    assert any(item.kind == SecuritySurfaceKind.AUTHORIZATION for item in frontier.executable)
    assert any(item.kind == SecuritySurfaceKind.STATE_TRANSITION for item in frontier.executable)


def test_reasoning_switches_to_frontier_when_capability_gap_has_other_executable_paths():
    h = Hypothesis("h1", "authorization boundary should hold")
    frontier = build_web2_security_frontier(model_with_reachable_surfaces())
    decision = select_next_web2_experiment(
        h,
        has_differential_support=False,
        has_causal_verification=False,
        capability_gap=True,
        frontier=frontier,
    )
    assert decision.kind == "SECURITY_FRONTIER"


def test_reasoning_repairs_capability_when_frontier_is_empty():
    h = Hypothesis("h1", "authorization boundary should hold")
    decision = select_next_web2_experiment(
        h,
        has_differential_support=False,
        has_causal_verification=False,
        capability_gap=True,
    )
    assert decision.kind == "CAPABILITY_REPAIR"
