from dataclasses import dataclass
from cydra.adapter_experiment import AdapterExperiment,ExperimentAction
from cydra.execution_adapter import AdapterCapability,AdapterObservation,AdapterRequest,AdapterStatus
from cydra.hypotheses import Hypothesis,HypothesisState
from cydra.web2_cycle import run_web2_authorization_cycle

@dataclass
class Fake:
    adapter_id:str="fake"; owner_status:int=200; comparison_status:int=200; body_hash:str="same"
    def capabilities(self): return (AdapterCapability("HTTP_REQUEST",True),)
    def execute(self,r): 
        s=self.owner_status if r.inputs["identity_id"]=="alice" else self.comparison_status
        return AdapterObservation(AdapterStatus.EXECUTED,r.action_id,{"status_code":s,"body_sha256":self.body_hash if s==200 else "denied"})

def h(): return Hypothesis("web2-auth:resource:1:endpoint:get","owner and comparison identity should have distinct authorization outcomes")
def e(): return AdapterExperiment("X-web2-auth:resource:1:endpoint:get",h().hypothesis_id,"https://authorized.example",(ExperimentAction("owner","http_request",{"identity_id":"alice"}),ExperimentAction("comparison","http_request",{"identity_id":"bob"})),("authorization",))

def test_cycle_updates_belief_from_identical_response():
    r=run_web2_authorization_cycle(h(),e(),Fake()); assert r.verification.state.value=="contradicted" and r.hypothesis.state==HypothesisState.CONTRADICTED and r.hypothesis.belief<0.5

def test_cycle_does_not_turn_failure_into_evidence():
    class Blocked(Fake):
        def execute(self,r): return AdapterObservation(AdapterStatus.UNAVAILABLE,r.action_id,error="blocked")
    r=run_web2_authorization_cycle(h(),e(),Blocked()); assert r.verification.state.value=="unresolved" and r.hypothesis.belief==0.5
