from cydra.web2_authorization import plan_ownership_differential
from cydra.web2_model import Web2EndpointModel,Web2IdentityModel,Web2ResourceModel,Web2TargetModel

def test_planner_creates_differential_experiment():
    m=Web2TargetModel("https://authorized.example"); m.add_identity(Web2IdentityModel("alice","Alice")); m.add_identity(Web2IdentityModel("bob","Bob")); m.add_resource(Web2ResourceModel("resource:1","Alice record","alice","1")); m.add_endpoint(Web2EndpointModel("endpoint:get","GET","/records/{id}",("resource:1",),"read"))
    p=plan_ownership_differential(m,owner_identity_id="alice",other_identity_id="bob",resource_id="resource:1",endpoint_id="endpoint:get")
    assert p.hypothesis.status=="proposed" and len(p.experiment.actions)==2 and p.experiment.actions[1].inputs["path"]=="/records/1"

def test_planner_requires_explicit_ownership():
    m=Web2TargetModel("https://authorized.example"); m.add_identity(Web2IdentityModel("alice","Alice")); m.add_identity(Web2IdentityModel("bob","Bob")); m.add_resource(Web2ResourceModel("resource:1","record","alice","1")); m.add_endpoint(Web2EndpointModel("endpoint:get","GET","/records/{id}",("resource:1",)))
    try: plan_ownership_differential(m,owner_identity_id="bob",other_identity_id="alice",resource_id="resource:1",endpoint_id="endpoint:get")
    except ValueError as e: assert "ownership" in str(e)
    else: raise AssertionError("planner must reject unsupported ownership")


def test_generator_creates_all_explicit_cross_identity_plans():
    from cydra.web2_authorization import generate_ownership_differential_plans
    m=Web2TargetModel("https://authorized.example")
    m.add_identity(Web2IdentityModel("alice","Alice"))
    m.add_identity(Web2IdentityModel("bob","Bob"))
    m.add_identity(Web2IdentityModel("carol","Carol"))
    m.add_resource(Web2ResourceModel("resource:1","Alice record","alice","1"))
    m.add_endpoint(Web2EndpointModel("endpoint:get","GET","/records/{id}",("resource:1",),"read"))
    plans=generate_ownership_differential_plans(m)
    assert len(plans)==2
    assert {p.experiment.actions[1].inputs["identity_id"] for p in plans}=={"bob","carol"}
    assert all(p.hypothesis.expected_impact=="UNAUTHORIZED_RESOURCE_ACCESS" for p in plans)


def test_generator_ignores_endpoints_without_explicit_resource_relation():
    from cydra.web2_authorization import generate_ownership_differential_plans
    m=Web2TargetModel("https://authorized.example")
    m.add_identity(Web2IdentityModel("alice","Alice"))
    m.add_identity(Web2IdentityModel("bob","Bob"))
    m.add_resource(Web2ResourceModel("resource:1","record","alice","1"))
    m.add_endpoint(Web2EndpointModel("endpoint:unrelated","GET","/health"))
    assert generate_ownership_differential_plans(m) == ()
