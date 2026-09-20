from __future__ import annotations
import argparse, json, tempfile
from pathlib import Path

from cydra.canonical_cycle import run_canonical_differential_cycle
from cydra.foundry import require_executed, run_foundry_test, test_path_for
from cydra.finding_gate import FindingCandidate, evaluate_finding_graph
from cydra.hypotheses import Hypothesis as CanonicalHypothesis
from cydra.impact import ImpactAssessment, ImpactLevel
from cydra.pipeline import investigate
from cydra.structural_cross_contract_economic import generate_cross_contract_economic_hypotheses
from cydra.cross_contract_economic_execution import generate_cross_contract_economic_test
from cydra.solidity_model import parse_solidity
from cydra.system_model import Edge, Node, SystemModel

V=Path("benchmarks/015_cross_contract_economic/Target.sol")
P=Path("benchmarks/015_cross_contract_economic/TargetPatched.sol")

def project(src, root):
    (root/"src").mkdir(parents=True); (root/"test").mkdir()
    (root/"foundry.toml").write_text("[profile.default]\nsrc='src'\ntest='test'\nlibs=[]\n",encoding="utf-8")
    (root/"src"/src.name).write_text(src.read_text(encoding="utf-8"),encoding="utf-8")

def run_side(source, h, label):
    with tempfile.TemporaryDirectory(prefix=f"cydra-cross-economic-{label}-") as tmp:
        root=Path(tmp)/"project"; project(source,root)
        model=parse_solidity(root/"src"/source.name)[-1]
        test=generate_cross_contract_economic_test(h,root/"test"/"CydraCrossContractEconomicTest.t.sol",f"../src/{source.name}")
        result=run_foundry_test(root,test,f"X-{h.hypothesis_id}",label)
        require_executed(result)
        return result

def canonical_model(h):
    model=SystemModel()
    cid="contract:Vault"; fid="function:Vault:syncStrategy"; iid=f"invariant:{h.invariant_id}"; hid=f"hypothesis:{h.hypothesis_id}"; oid="observation:cross-contract-backing"
    model.add_node(Node(cid,"contract","Vault",{"provenance":"solidity_model"}))
    model.add_node(Node(fid,"function","syncStrategy",{"contract":"Vault","provenance":"solidity_model"}))
    model.add_node(Node(iid,"invariant",h.claim,{"status":"inferred","confidence":0.80,"provenance":"cross-contract economic reasoning"}))
    model.add_node(Node(hid,"hypothesis",h.claim,{"belief":0.5,"state":"unresolved","invariant_id":iid,"provenance":"cross-contract economic reasoning"}))
    model.add_node(Node(oid,"observation","compare internal accounting against actual asset backing after strategy synchronization",{"status":"planned","hypothesis_id":hid,"target_function_id":fid,"binding_status":"bound","experiment_binding":{"hypothesis_id":hid,"observation_id":oid,"target_function_id":fid},"provenance":"cross-contract economic experiment"}))
    model.add_edge(Edge(iid,"informs",hid,{})); model.add_edge(Edge(oid,"tests",hid,{}))
    return model,CanonicalHypothesis(h.hypothesis_id,h.claim,0.5),oid

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--output",type=Path,default=Path("backtest-artifacts/cross-contract-economic")); args=ap.parse_args()
    root=Path(__file__).resolve().parents[1]
    r=investigate(root/V,target="unfamiliar cross-contract economic conservation",reasoning_surfaces=(generate_cross_contract_economic_hypotheses,))
    hs=[h for h in r.hypotheses if h.invariant_id.startswith("INV-CROSS-CONTRACT-ECONOMIC-")]
    if not hs: raise SystemExit("No cross-contract economic hypothesis extracted")
    h=hs[0]; e=next(e for e in r.experiments if e.hypothesis_id==h.hypothesis_id)
    vulnerable=run_side(root/V,h,"vulnerable"); patched=run_side(root/P,h,"patched")
    model,ch,oid=canonical_model(h)
    cycle=run_canonical_differential_cycle(model,hypothesis=ch,observation_id=oid,vulnerable=vulnerable,patched=patched,outcome_id="cross-contract-economic-differential")
    impact=ImpactAssessment(ImpactLevel.HIGH,"economic solvency / asset backing","Internal asset accounting can exceed actual backing across a contract boundary, creating unbacked claims.",("caller can trigger synchronization","later withdrawals trust the inflated internal accounting"),cycle.causal_verification.evidence_ids)
    gate=evaluate_finding_graph(model,candidate=FindingCandidate(True,False,True,True,cycle.causal_verification.state.value=="verified",impact.assessed,True),finding_id=f"F-CROSS-CONTRACT-{h.target_function}",hypothesis_id=f"hypothesis:{h.hypothesis_id}",evidence_ids=cycle.causal_verification.evidence_ids,causal_chain_id=cycle.causal_chain.chain_id)
    args.output.mkdir(parents=True,exist_ok=True)
    payload={"hypothesis":h.__dict__,"experiment":e.__dict__,"vulnerable":vulnerable.__dict__,"patched":patched.__dict__,"causal_verification":cycle.causal_verification.__dict__,"finding_gate":{"decision":gate.decision.value,"reasons":list(gate.reasons)}}
    (args.output/"result.json").write_text(json.dumps(payload,indent=2,default=str)+"\n")
    print(json.dumps(payload,indent=2,default=str))
    return 0 if gate.decision.value=="READY" else 1
if __name__=="__main__": raise SystemExit(main())
