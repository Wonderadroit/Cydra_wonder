from cydra.web2_model import Web2EndpointModel,Web2IdentityModel,Web2ResourceModel,Web2TargetModel

def build_model():
    m=Web2TargetModel("https://authorized.example"); m.add_identity(Web2IdentityModel("alice","Alice")); m.add_identity(Web2IdentityModel("bob","Bob")); m.add_resource(Web2ResourceModel("resource:1","Alice record","alice","1")); m.add_endpoint(Web2EndpointModel("endpoint:get-record","GET","/records/{id}",("resource:1",),"read")); return m

def test_model_records_explicit_ownership():
    r=build_model().infer_ownership_authorization(); assert len(r)==1 and r[0].identity_id=="alice" and r[0].expected=="allow_owner"

def test_cross_identity_pairs_are_planning_candidates_not_findings():
    m=build_model(); assert m.candidate_cross_identity_pairs()==(("alice","bob","resource:1"),) and not m.observations

def test_model_rejects_unknown_resource_owner():
    m=Web2TargetModel("https://authorized.example")
    try: m.add_resource(Web2ResourceModel("resource:1","record","missing"))
    except ValueError as e: assert "owner" in str(e)
    else: raise AssertionError("unknown owner should be rejected")
