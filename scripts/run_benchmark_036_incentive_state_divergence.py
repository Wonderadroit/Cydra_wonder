from __future__ import annotations
import argparse, json, shutil, subprocess, tempfile
from pathlib import Path
from cydra.pipeline import investigate
from cydra.hypothesis_selection import select_next_hypothesis
from cydra.canonical_cycle import run_canonical_differential_cycle
from cydra.finding_gate import FindingCandidate, evaluate_finding_graph
from cydra.impact import ImpactAssessment, ImpactLevel
from cydra.models import Hypothesis as ModelHypothesis
from cydra.system_model import Edge, Node, SystemModel

TARGET_PATH=Path("benchmarks/036_incentive_state_divergence/Target.sol")
TEST=r"""
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
import "../Target.sol";
contract IncentiveTest {
    function run(address target) external payable {
        (bool a,) = target.call(abi.encodeWithSignature("requestWork()"));
        require(a);
        (bool b,) = target.call(abi.encodeWithSignature("commitWork()"));
        require(b);
        require(address(this).balance > 0, "reward not captured");
    }
    receive() external payable {}
}
"""

def setup(dest: Path):
    subprocess.run(("forge","init","--force",str(dest)),check=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    subprocess.run(("forge","install","foundry-rs/forge-std","--no-commit"),cwd=dest,check=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    (dest/"Target.sol").write_text(TARGET_PATH.read_text(encoding="utf-8"),encoding="utf-8")
    (dest/"test").mkdir(exist_ok=True)
    return dest

def run_fixture(patched: bool, label: str):
    with tempfile.TemporaryDirectory(prefix="cydra-036-") as t:
        root=setup(Path(t)/"project")
        source=TEST.replace("requestWork()", "requestWork{value: 2 ether}()") if patched else TEST
        source=source.replace("contract IncentiveTest", "contract IncentiveTest")
        harness=(
            "// SPDX-License-Identifier: MIT\npragma solidity ^0.8.20;\n"
            "import \"forge-std/Test.sol\"; import \"../Target.sol\";\n"
            "contract C is Test { function test() public { "
            + ("IncentiveQueuePatched target = new IncentiveQueuePatched{value: 5 ether}();" if patched else "IncentiveQueue target = new IncentiveQueue{value: 2 ether}();")
            + " uint256 before = address(this).balance; (bool a,) = address(target).call"
            + ("(abi.encodeWithSignature(\"requestWork()\"));" if patched else "(abi.encodeWithSignature(\"requestWork()\"));")
            + " require(a); "
            + " uint256 before = address(this).balance; (bool c,) = address(target).call(abi.encodeWithSignature(\"commitWork()\")); require(c); require(address(this).balance > before, \"no reward\"); } receive() external payable {} }\n"
        )
        (root/"test"/"Incentive.t.sol").write_text(harness,encoding="utf-8")
        p=subprocess.run(("forge","test","--match-test","test","-vvv"),cwd=root,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        return {"experiment_id":"X-"+label,"executed":True,"tests_run":1,"tests_failed":0 if p.returncode==0 else 1,"status":"PASS" if p.returncode==0 else "FAIL","exit_code":p.returncode,"stdout":p.stdout[-12000:],"stderr":""}

def canonical_model(h):
    m=SystemModel()
    iid="invariant:"+h.invariant_id; hid="hypothesis:"+h.hypothesis_id; oid="incentive-cost-reward-gap"
    m.add_node(Node("contract:IncentiveQueue","contract","IncentiveQueue",{"provenance":"historical-style incentive fixture"}))
    m.add_node(Node("contract:IncentiveQueuePatched","contract","IncentiveQueuePatched",{"provenance":"causal control"}))
    m.add_node(Node("function:IncentiveQueue:"+h.target_function,"function",h.target_function,{}))
    m.add_node(Node(iid,"invariant",h.claim,{"status":"inferred","confidence":0.72}))
    m.add_node(Node(hid,"hypothesis",h.claim,{"belief":0.5}))
    m.add_node(Node("observation:"+oid,"observation","caller cost versus payout reward",{"status":"planned","hypothesis_id":hid,"target_function_id":"function:IncentiveQueue:"+h.target_function,"binding_status":"bound","experiment_binding":{"hypothesis_id":hid,"observation_id":"observation:"+oid,"target_function_id":"function:IncentiveQueue:"+h.target_function}}))
    m.add_edge(Edge(iid,"informs",hid,{})); m.add_edge(Edge("observation:"+oid,"tests",hid,{}))
    return m, ModelHypothesis(h.hypothesis_id,h.claim,0.5), oid

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--output",type=Path,default=Path("backtest-artifacts/benchmark-036-incentive-state-divergence")); args=ap.parse_args()
    investigation=investigate(TARGET_PATH,target="benchmark-036-incentive-state-divergence")
    selection=select_next_hypothesis(investigation.hypotheses,investigation.invariants,investigation.experiments)
    h=selection.hypothesis
    if h.invariant_id != "INV-INCENTIVE-LIVENESS-commitWork": raise SystemExit("strict blind selector did not choose incentive-liveness hypothesis: "+h.hypothesis_id)
    experiment=next(e for e in investigation.experiments if e.hypothesis_id==h.hypothesis_id)
    vulnerable=run_fixture(False,"blind-vulnerable"); patched=run_fixture(True,"patched")
    independent_vulnerable=run_fixture(False,"independent-vulnerable"); independent_patched=run_fixture(True,"independent-patched")
    model,ch,oid=canonical_model(h)
    class E:
        def __init__(self,p): self.__dict__.update(p)
    cycle=run_canonical_differential_cycle(model,hypothesis=ch,observation_id=oid,vulnerable=E(vulnerable),patched=E(patched),outcome_id="benchmark-036-incentive-differential")
    reproduction=independent_vulnerable["status"]=="FAIL" and independent_patched["status"]=="PASS"
    impact=ImpactAssessment(ImpactLevel.MEDIUM,"incentive extraction","A permissionless caller can manufacture payout-eligible work without bearing the intended request cost and capture protocol-funded incentives.",("requestWork creates work without value transfer","commitWork pays a fixed reward to msg.sender"),cycle.causal_verification.evidence_ids)
    gate=evaluate_finding_graph(model,candidate=FindingCandidate(True,False,True,True,cycle.causal_verification.state.value=="verified",impact.assessed,reproduction),finding_id="F-BENCHMARK-036-"+h.target_function,hypothesis_id="hypothesis:"+h.hypothesis_id,evidence_ids=cycle.causal_verification.evidence_ids,causal_chain_id=cycle.causal_chain.chain_id)
    payload={"blind_selection":{"hypothesis":h.__dict__,"score":selection.score},"experiment":experiment.__dict__,"vulnerable":vulnerable,"patched":patched,"causal_verification":cycle.causal_verification.__dict__,"independent_vulnerable":independent_vulnerable,"independent_patched":independent_patched,"reproduction_verified":reproduction,"finding_gate":gate.decision.value}
    args.output.mkdir(parents=True,exist_ok=True); (args.output/"result.json").write_text(json.dumps(payload,indent=2,default=str)+"\n"); print(json.dumps(payload,indent=2,default=str)); return 0 if gate.decision.value=="READY" else 1

if __name__=="__main__": raise SystemExit(main())
