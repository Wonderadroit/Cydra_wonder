from __future__ import annotations
import json, shutil, tempfile
from pathlib import Path
from cydra.pipeline import investigate
from cydra.structural_temporal import generate_temporal_precondition_hypotheses
from cydra.reasoning import plan_temporal_precondition_experiment
from cydra.temporal_precondition_execution import generate_temporal_precondition_test
from cydra.foundry import run_foundry_test, require_executed, test_path_for
from cydra.canonical_cycle import run_canonical_differential_cycle
from cydra.finding_gate import FindingCandidate,evaluate_finding_graph
from cydra.hypotheses import Hypothesis as CH
from cydra.system_model import SystemModel,Node,Edge
from cydra.impact import ImpactAssessment,ImpactLevel
V=Path("benchmarks/010_temporal_precondition/TemporalPreconditionTarget.sol")
P=Path("benchmarks/010_temporal_precondition/TemporalPreconditionTargetPatched.sol")
def project(src,root):
 (root/"src").mkdir(parents=True);(root/"test").mkdir()
 (root/"foundry.toml").write_text("[profile.default]\nsrc='src'\ntest='test'\nlibs=[]\n")
 shutil.copy2(src,root/"src"/src.name)
def side(src,h,e,label):
 with tempfile.TemporaryDirectory(prefix="cydra-temporal-") as t:
  root=Path(t)/"p";project(src,root)
  from cydra.solidity_model import parse_solidity
  cm=parse_solidity(root/"src"/src.name)[0]
  g=generate_temporal_precondition_test(h,cm,f"../src/{src.name}",cm.name,test_path_for(root,f"generated/{h.hypothesis_id}.t.sol"),experiment=e)
  r=run_foundry_test(root,g,e.experiment_id,label);require_executed(r);return r

def main():
 root=Path(__file__).resolve().parents[1];v=root/V;p=root/P
 result=investigate(v,target="OpenZeppelin TimelockController historical temporal-precondition extraction",reasoning_surfaces=(generate_temporal_precondition_hypotheses,),experiment_planner=plan_temporal_precondition_experiment)
 hs=[h for h in result.hypotheses if h.invariant_id.startswith("INV-TEMPORAL-PRECONDITION-")]
 if not hs: raise SystemExit("No temporal precondition hypothesis extracted")
 h=hs[0];e=next(x for x in result.experiments if x.hypothesis_id==h.hypothesis_id)
 vr=side(v,h,e,"temporal-vulnerable");pr=side(p,h,e,"temporal-patched")
 m=SystemModel();cid=f"contract:{result.contracts[0].name}";fid=f"function:{result.contracts[0].name}:{h.target_function}";iid=f"invariant:{h.invariant_id}";hid=f"hypothesis:{h.hypothesis_id}";oid="temporal-precondition"
 m.add_node(Node(cid,"contract",result.contracts[0].name,{}));m.add_node(Node(fid,"function",h.target_function,{}));m.add_node(Node(iid,"invariant",h.claim,{"status":"inferred"}));m.add_node(Node(hid,"hypothesis",h.claim,{"belief":0.5}));m.add_node(Node(f"observation:{oid}","observation","precondition-before-external-call",{"status":"planned"}));m.add_edge(Edge(iid,"informs",hid,{}));m.add_edge(Edge(f"observation:{oid}","tests",hid,{}))
 cyc=run_canonical_differential_cycle(m,hypothesis=CH(h.hypothesis_id,h.claim,0.5),observation_id=oid,vulnerable=vr,patched=pr,outcome_id="temporal-precondition-differential")
 impact=ImpactAssessment(ImpactLevel.HIGH,"timelocked operation execution boundary","A precondition intended to prevent premature execution can become true during the same transition because an external call mutates the readiness state.","caller can reach the transition; callee can affect readiness state",cyc.causal_verification.evidence_ids)
 gate=evaluate_finding_graph(m,candidate=FindingCandidate(True,False,True,True,cyc.causal_verification.state.value=="verified",impact.assessed,True),finding_id=f"F-TEMPORAL-{h.target_function}",hypothesis_id=hid,evidence_ids=cyc.causal_verification.evidence_ids,causal_chain_id=cyc.causal_chain.chain_id)
 out={"hypothesis":h.__dict__,"experiment":e.__dict__,"vulnerable":vr.__dict__,"patched":pr.__dict__,"causal":cyc.causal_verification.__dict__,"finding_gate":gate.decision.value,"reasons":list(gate.reasons)};print(json.dumps(out,indent=2,default=str));return 0 if gate.decision.value=="READY" else 1
if __name__=="__main__": raise SystemExit(main())
