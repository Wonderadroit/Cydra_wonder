from dataclasses import dataclass
from cydra.adapter_experiment import ExperimentAction, bind_adapter_experiment, execute_adapter_experiment
from cydra.execution_adapter import AdapterCapability, AdapterObservation, AdapterRequest, AdapterStatus
from cydra.hypotheses import Hypothesis

@dataclass
class RecordingAdapter:
    adapter_id:str="test"; calls:list=None
    def __post_init__(self): self.calls=[] if self.calls is None else self.calls
    def capabilities(self): return (AdapterCapability("TEST",True),)
    def execute(self,request): self.calls.append(request); return AdapterObservation(AdapterStatus.EXECUTED,request.action_id,{"ok":True})

def hypothesis(): return Hypothesis("H-WEB2-AUTH-1","identity B must not access identity A's private resource",invariant_id="I-AUTH",target_function="resource",attacker_capability="authenticated second identity",expected_impact="private data disclosure")

def test_experiment_binds_hypothesis_and_executes_in_order():
    h=hypothesis(); e=bind_adapter_experiment(h,target="https://authorized.example",actions=(ExperimentAction("a1","http_request"),ExperimentAction("a2","http_request")),discriminates=("authorized_access","cross_identity_access"))
    a=RecordingAdapter(); o=execute_adapter_experiment(e,a)
    assert [x.action_id for x in o]==["a1","a2"]; assert a.calls[1].metadata["hypothesis_id"]==h.hypothesis_id

def test_adapter_gap_stops_experiment():
    class Blocking:
        adapter_id="blocked"
        def capabilities(self): return ()
        def execute(self,r): return AdapterObservation(AdapterStatus.UNAVAILABLE,r.action_id,error="missing capability")
    h=hypothesis(); e=bind_adapter_experiment(h,target="https://authorized.example",actions=(ExperimentAction("a1","unsupported"),ExperimentAction("a2","http_request")),discriminates=("x",))
    o=execute_adapter_experiment(e,Blocking()); assert len(o)==1 and o[0].status==AdapterStatus.UNAVAILABLE
