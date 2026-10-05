from dataclasses import dataclass
from cydra.adapter_experiment import AdapterExperiment,ExperimentAction
from cydra.execution_adapter import AdapterObservation,AdapterStatus,AdapterRequest
from cydra.web2_replay import replay_authorization_experiment

@dataclass
class Fake:
    adapter_id:str="fake"
    def capabilities(self): return ()
    def execute(self,r:AdapterRequest): return AdapterObservation(AdapterStatus.EXECUTED,r.action_id,{"status_code":200,"body_sha256":"same"})

def e(method="GET"): return AdapterExperiment("x","h1","https://example.test",(ExperimentAction("owner","http_request",{"method":method,"identity_id":"alice"}),ExperimentAction("other","http_request",{"method":method,"identity_id":"bob"})),("authorization",))

def test_read_replay_runs_twice():
    r=replay_authorization_experiment(e(),Fake()); assert len(r.owner)==2 and len(r.comparison)==2

def test_mutating_replay_fails_closed():
    r=replay_authorization_experiment(e("POST"),Fake()); assert r.owner[0].status==AdapterStatus.UNAVAILABLE
