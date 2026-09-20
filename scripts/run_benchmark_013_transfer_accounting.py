from __future__ import annotations
import json,shutil,tempfile
from pathlib import Path
from cydra.pipeline import investigate
from cydra.structural_transfer_accounting import generate_transfer_accounting_hypotheses
from cydra.reasoning import plan_transfer_accounting_experiment
from cydra.transfer_accounting_execution import generate_transfer_accounting_test
from cydra.foundry import run_foundry_test,require_executed,test_path_for
from cydra.canonical_cycle import run_canonical_differential_cycle
from cydra.finding_gate import FindingCandidate,evaluate_finding_graph
from cydra.hypotheses import Hypothesis as CH
from cydra.system_model import SystemModel,Node,Edge
from cydra.impact import ImpactAssessment,ImpactLevel

V=Path("benchmarks/013_transfer_accounting/FeeTransferAccountingTarget.sol"); P=Path("benchmarks/013_transfer_accounting/FeeTransferAccountingTargetPatched.sol")
def project(src,root):
    (root/"src").mkdir(parents=True); (root/"test").mkdir()
    (root/"foundry.toml").write_text("[profile.default]\nsrc='src'\ntest='test'\nlibs=[]\n")
    shutil.copy2(src,root/"src"/src.name)
def side(src,h,e,label):
    with tempfile.TemporaryDirectory(prefix="cydra-transfer-accounting-") as tmp:
        root=Path(tmp)/"p"; project(src,root)
        from cydra.solidity_model import parse_solidity
        cs=parse_solidity(root/"src"/src.name)
        target=next(c for c in cs if any(f.name==h.target_function for f in c.functions))
        tp=test_path_for(root,f"generated/{h.hypothesis_id}.t.sol")
        generated=generate_transfer_accounting_test(h,target,f"../src/{src.name}",target.name,"FeeTransferToken",tp,experiment=e)
        result=run_foundry_test(root,generated,e.experiment_id,label)\n        if not result.executed: print(json.dumps(result.__dict__,indent=2,default=str))\n        require_executed(result); return result
def main():
    root=Path(__file__).resolve().parents[1]
    r=investigate(root/V,target="historical fee-on-transfer accounting extracted regression",reasoning_surfaces=(generate_transfer_accounting_hypotheses,),experiment_planner=plan_transfer_accounting_experiment)
    hs=[h for h in r.hypotheses if h.invariant_id.startswith("INV-TRANSFER-ACCOUNTING-")]
    if not hs: raise SystemExit("No transfer-accounting hypothesis extracted")
    h=hs[0]; e=next(x for x in r.experiments if x.hypothesis_id==h.hypothesis_id)
    v=side(V,h,e,"transfer-accounting-vulnerable"); p=side(P,h,e,"transfer-accounting-patched")
    c=next(c for c in r.contracts if any(f.name==h.target_function for f in c.functions))
    m=SystemModel(); cid=f"contract:{c.name}"; fid=f"function:{c.name}:{h.target_function}"; iid=f"invariant:{h.invariant_id}"; hid=f"hypothesis:{h.hypothesis_id}"; oid="transfer-accounting"
    for n in (Node(cid,"contract",c.name,{}),Node(fid,"function",h.target_function,{}),Node(iid,"invariant",h.claim,{"status":"inferred"}),Node(hid,"hypothesis",h.claim,{"belief":0.5})): m.add_node(n)
    m.add_node(Node(f"observation:{oid}","observation","inbound transfer credit equals actual received balance delta",{"status":"planned","hypothesis_id":hid,"target_function_id":fid,"binding_status":"bound","experiment_binding":{"hypothesis_id":hid,"observation_id":f"observation:{oid}","target_function_id":fid}}))
    m.add_edge(Edge(iid,"informs",hid,{})); m.add_edge(Edge(f"observation:{oid}","tests",hid,{}))
    cycle=run_canonical_differential_cycle(m,hypothesis=CH(h.hypothesis_id,h.claim,0.5),observation_id=oid,vulnerable=v,patched=p,outcome_id="transfer-accounting-differential")
    impact=ImpactAssessment(ImpactLevel.HIGH,"internal credit can exceed assets actually received","A receiving contract can record more value than it holds, making later withdrawals undercollateralized.","caller can supply a token whose transfer delivers less than the requested amount",cycle.causal_verification.evidence_ids)
    gate=evaluate_finding_graph(m,candidate=FindingCandidate(True,False,True,True,cycle.causal_verification.state.value=="verified",impact.assessed,True),finding_id=f"F-TRANSFER-ACCOUNTING-{h.target_function}",hypothesis_id=hid,evidence_ids=cycle.causal_verification.evidence_ids,causal_chain_id=cycle.causal_chain.chain_id)
    print(json.dumps({"hypothesis":h.__dict__,"experiment":e.__dict__,"vulnerable":v.__dict__,"patched":p.__dict__,"causal":cycle.causal_verification.__dict__,"finding_gate":gate.decision.value,"reasons":list(gate.reasons)},indent=2,default=str))
    return 0 if gate.decision.value=="READY" else 1
if __name__=="__main__": raise SystemExit(main())

