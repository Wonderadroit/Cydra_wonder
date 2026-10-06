from cydra.hypotheses import Hypothesis,HypothesisState
from cydra.web2_causal import Web2CausalVerification
from cydra.web2_reasoning import apply_causal_verification,select_next_web2_experiment

def test_causal_verification_updates_hypothesis():
    h=Hypothesis("h1","non-owner can access owner resource"); v=Web2CausalVerification(HypothesisState.CAUSALLY_ESTABLISHED,0.95,"reproduced",("a",)); u=apply_causal_verification(h,v); assert u.state==HypothesisState.CAUSALLY_ESTABLISHED and u.belief==0.95

def test_selector_prefers_causal_replay():
    h=Hypothesis("h1","authorization must separate identities"); d=select_next_web2_experiment(h,has_differential_support=True,has_causal_verification=False,capability_gap=False); assert d.kind=="CAUSAL_REPLAY"

def test_selector_repairs_capability_first():
    h=Hypothesis("h1","authorization must separate identities"); d=select_next_web2_experiment(h,has_differential_support=True,has_causal_verification=False,capability_gap=True); assert d.kind=="CAPABILITY_REPAIR"


def test_security_hypothesis_planner_uses_only_explicit_model_relations():
    from cydra.web2_reasoning import generate_web2_security_hypotheses
    from cydra.web2_model import Web2EndpointModel, Web2IdentityModel, Web2ResourceModel, Web2TargetModel
    m=Web2TargetModel("https://authorized.example")
    m.add_identity(Web2IdentityModel("alice","Alice"))
    m.add_identity(Web2IdentityModel("bob","Bob"))
    m.add_resource(Web2ResourceModel("resource:1","record","alice","1"))
    m.add_endpoint(Web2EndpointModel("endpoint:get","GET","/records/{id}",("resource:1",)))
    result=generate_web2_security_hypotheses(m)
    assert len(result.plans)==1
    assert result.plans[0].hypothesis.expected_impact=="UNAUTHORIZED_RESOURCE_ACCESS"
    assert result.capability_gaps==()

def test_security_hypothesis_planner_reports_missing_capability():
    from cydra.web2_reasoning import generate_web2_security_hypotheses
    from cydra.web2_model import Web2EndpointModel, Web2IdentityModel, Web2ResourceModel, Web2TargetModel
    m=Web2TargetModel("https://authorized.example")
    m.add_identity(Web2IdentityModel("alice","Alice"))
    m.add_identity(Web2IdentityModel("bob","Bob"))
    m.add_resource(Web2ResourceModel("resource:1","record","alice",None))
    m.add_endpoint(Web2EndpointModel("endpoint:get","GET","/records/{id}",("resource:1",)))
    result=generate_web2_security_hypotheses(m)
    assert result.plans==()
    assert result.capability_gaps

def test_discovery_result_flows_into_security_hypothesis_planning():
    from cydra.web2_discovery import Web2DiscoveryResult
    from cydra.web2_materialization import Web2ResourceProvenance
    from cydra.web2_model import Web2EndpointModel, Web2IdentityModel, Web2ResourceModel, Web2TargetModel
    from cydra.web2_reasoning import generate_web2_hypotheses_from_discovery
    m=Web2TargetModel("https://authorized.example")
    m.add_identity(Web2IdentityModel("alice","Alice"))
    m.add_identity(Web2IdentityModel("bob","Bob"))
    m.add_resource(Web2ResourceModel("resource:1","record","alice",None))
    m.add_endpoint(Web2EndpointModel("endpoint:get","GET","/records/{id}",("resource:1",)))
    discovery=Web2DiscoveryResult(model=m, observations=(), discovered_paths=(), resource_provenance=(
        Web2ResourceProvenance("resource:1","1","endpoint:get","test-observation","id"),
    ))
    result=generate_web2_hypotheses_from_discovery(discovery)
    assert len(result.plans)==1
    assert result.plans[0].experiment.actions[0].inputs["path"]=="/records/1"
    assert result.capability_gaps==()

def test_discovery_capability_gaps_are_published_into_hypothesis_planning():
    from cydra.web2_discovery import Web2DiscoveryResult
    from cydra.web2_reasoning import generate_web2_hypotheses_from_discovery
    from cydra.web2_model import Web2TargetModel
    discovery=Web2DiscoveryResult(
        model=Web2TargetModel("https://authorized.example"),
        observations=(),
        discovered_paths=(),
        capability_gaps=("SERVICE_ORIGIN_RESOLUTION",),
    )
    result=generate_web2_hypotheses_from_discovery(discovery)
    assert result.plans==()
    assert result.capability_gaps==("SERVICE_ORIGIN_RESOLUTION",)


def test_resource_state_gap_creates_non_executable_repair_plan():
    from cydra.web2_discovery import Web2DiscoveryResult
    from cydra.web2_reasoning import generate_web2_capability_repair_plans
    from cydra.web2_model import Web2TargetModel
    discovery=Web2DiscoveryResult(
        model=Web2TargetModel("https://authorized.example"),
        observations=(),
        discovered_paths=(),
        capability_gaps=("RESOURCE_STATE_ACQUISITION",),
    )
    plans=generate_web2_capability_repair_plans(discovery)
    assert len(plans)==1
    assert plans[0].capability=="RESOURCE_STATE_ACQUISITION"
    assert not plans[0].executable
    assert "resource_identifier_observation" in plans[0].required_capabilities


def test_resource_state_repair_waits_for_frontier_when_incomplete():
    from cydra.web2_discovery import Web2CapabilityState, Web2DiscoveryResult
    from cydra.web2_reasoning import generate_web2_capability_repair_plans
    from cydra.web2_model import Web2TargetModel
    discovery = Web2DiscoveryResult(
        model=Web2TargetModel("https://authorized.example"),
        observations=(),
        discovered_paths=(),
        capability_gaps=("RESOURCE_STATE_ACQUISITION",),
        capability_states=(
            Web2CapabilityState(
                "RESOURCE_STATE_ACQUISITION",
                "INCOMPLETE_FRONTIER",
                attempted_strategies=("response_state",),
                remaining_strategies=("javascript_frontier",),
                reason="more target-declared code remains",
            ),
        ),
    )
    plan = generate_web2_capability_repair_plans(discovery)[0]
    assert plan.state == "INCOMPLETE_FRONTIER"
    assert plan.required_capabilities == ("javascript_frontier",)
    assert "Do not patch resource extraction" in plan.reason
