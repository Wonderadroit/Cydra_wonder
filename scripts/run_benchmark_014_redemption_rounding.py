from __future__ import annotations
import argparse, json, tempfile
from pathlib import Path
from cydra.canonical_cycle import run_canonical_differential_cycle
from cydra.foundry import require_executed, run_foundry_test, test_path_for
from cydra.finding_gate import FindingCandidate, evaluate_finding_graph
from cydra.hypotheses import Hypothesis as CanonicalHypothesis
from cydra.impact import ImpactAssessment, ImpactLevel
from cydra.pipeline import investigate
from cydra.solidity_model import parse_solidity
from cydra.redemption_rounding_execution import generate_redemption_rounding_test
from cydra.system_model import Edge, Node, SystemModel

V=Path("benchmarks/014_redemption_rounding/RedemptionRoundingTarget.sol")
P=Path("benchmarks/014_redemption_rounding/RedemptionRoundingTargetPatched.sol")

def project(src, root):
    (root/"src").mkdir(parents=True); (root/"test").mkdir()
    (root/"foundry.toml").write_text("[profile.default]\nsrc='src'\ntest='test'\nlibs=[]\n",encoding="utf-8")
    (root/"src"/src.name).write_text(src.read_text(encoding="utf-8"),encoding="utf-8")

def run_side(source, hypothesis, experiment, label, expected=2):
    with tempfile.TemporaryDirectory(prefix=f"cydra-redemption-{label}-") as tmp:
        root=Path(tmp)/"project"; project(source,root)
        model=parse_solidity(root/"src"/source.name)[0]
        generated=generate_redemption_rounding_test(hypothesis,model,f"../src/{source.name}",model.name,root/"test"/f"{hypothesis.hypothesis_id}.t.sol",experiment,expected)
        result=run_foundry_test(root,generated,experiment.experiment_id,label)
        require_executed(result)
        return result

def canonical_model(hypothesis, contract_name):
    model=SystemModel()
    cid=f"contract:{contract_name}"; fid=f"function:{contract_name}:{hypothesis.target_function}"
    iid=f"invariant:{hypothesis.invariant_id}"; hid=f"hypothesis:{hypothesis.hypothesis_id}"
    oid=f"OBS-REDEMPTION-{contract_name}"
    model.add_node(Node(cid,"contract",contract_name,{"provenance":"solidity_model"}))
    model.add_node(Node(fid,"function",hypothesis.target_function,{"contract":contract_name,"provenance":"solidity_model"}))
    model.add_node(Node(iid,"invariant", "Required share burn must round conservatively for requested withdrawals.",{"status":"inferred","confidence":0.78,"provenance":"structural redemption-rounding reasoning"}))
    model.add_node(Node(hid,"hypothesis",hypothesis.claim,{"belief":0.5,"state":"unresolved","invariant_id":iid,"provenance":"structural redemption-rounding reasoning"}))
    model.add_node(Node(f"observation:{oid}","observation","Execute the withdrawal at a fractional share boundary.",{"status":"planned","provenance":"structural redemption-rounding experiment"}))
    model.add_edge(Edge(iid,"informs",hid,{"provenance":"structural redemption-rounding reasoning"}))
    model.add_edge(Edge(f"observation:{oid}","targets",iid,{"provenance":"structural redemption-rounding reasoning"}))
    model.add_edge(Edge(f"observation:{oid}","tests",hid,{"provenance":"structural redemption-rounding reasoning"}))
    return model,CanonicalHypothesis(hypothesis.hypothesis_id,hypothesis.claim,0.5),oid

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--output",type=Path,default=Path("backtest-artifacts/redemption-rounding")); args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    result=investigate(root/V,target="historical Onyx-style empty-market redemption-rounding extraction")
    hs=[h for h in result.hypotheses if h.invariant_id.startswith("INV-REDEMPTION-ROUNDING-")]
    if not hs: raise SystemExit("No redemption-rounding hypothesis extracted")
    h=hs[0]; e=next(x for x in result.experiments if x.hypothesis_id==h.hypothesis_id)
    vulnerable=run_side(root/V,h,e,"redemption-vulnerable",2)
    patched=run_side(root/P,h,e,"redemption-patched",2)
    model,ch,oid=canonical_model(h,result.contracts[0].name)
    cycle=run_canonical_differential_cycle(model,hypothesis=ch,observation_id=oid,vulnerable=vulnerable,patched=patched,outcome_id="redemption-rounding-differential")
    impact=ImpactAssessment(ImpactLevel.HIGH,"asset redemption/accounting integrity","Rounding the required receipt-unit burn down can let a withdrawal remove more assets than the surrendered share value warrants at extreme exchange rates.",("exchange rate can become highly inflated relative to share supply","withdrawal amount is caller-controlled"),cycle.causal_verification.evidence_ids)
    gate=evaluate_finding_graph(model,candidate=FindingCandidate(True,False,True,True,cycle.causal_verification.state.value=="verified",impact.assessed,True),finding_id=f"F-REDEMPTION-{h.target_function}",hypothesis_id=f"hypothesis:{h.hypothesis_id}",evidence_ids=cycle.causal_verification.evidence_ids,causal_chain_id=cycle.causal_chain.chain_id)
    args.output.mkdir(parents=True,exist_ok=True)
    payload={"target":"historical Onyx-style extracted regression","hypothesis":h.__dict__,"experiment":e.__dict__,"execution":{"vulnerable":vulnerable.__dict__,"patched":patched.__dict__},"canonical_cycle":{"verification":cycle.verification.__dict__,"causal_chain":cycle.causal_chain.__dict__,"causal_verification":cycle.causal_verification.__dict__},"impact":impact.__dict__,"finding_gate":{"decision":gate.decision.value,"reasons":list(gate.reasons)}}
    (args.output/"result.json").write_text(json.dumps(payload,indent=2,default=str)+"\n",encoding="utf-8")
    print(json.dumps(payload,indent=2,default=str))
    return 0 if gate.decision.value=="READY" else 1
if __name__=="__main__": raise SystemExit(main())
