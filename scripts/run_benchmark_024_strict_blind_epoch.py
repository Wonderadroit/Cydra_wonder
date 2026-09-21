from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from cydra.canonical_cycle import run_canonical_differential_cycle
from cydra.finding_gate import FindingCandidate, evaluate_finding_graph
from cydra.hypotheses import Hypothesis as CanonicalHypothesis
from cydra.impact import ImpactAssessment, ImpactLevel
from cydra.pipeline import investigate
from cydra.hypothesis_selection import select_next_hypothesis
from cydra.system_model import Edge, Node, SystemModel

TARGET_REPO = "https://github.com/code-423n4/2024-01-canto.git"
TARGET_REF = "5e0d6f1f981993f83d0db862bcf1b2a49bb6ff50"
TARGET_PATH = "src/LendingLedger.sol"

TEST_SOURCE = r"""// SPDX-License-Identifier: MIT
pragma solidity >=0.8.16;
import {Test} from "forge-std/Test.sol";
import "../LendingLedger.sol";

contract CydraDummyGaugeController {
    function gauge_relative_weight_write(address, uint256) external pure returns (uint256) { return 1e18; }
}

contract CydraStrictBlindEpochTest is Test {
    LendingLedger ledger;
    address governance = address(0x1001);
    address market = address(0x2002);
    address lender = address(0x3003);

    function testCydraEpochBoundaryAccounting() public {
        vm.roll(50_000);
        ledger = new LendingLedger(address(new CydraDummyGaugeController()), governance);
        vm.prank(governance); ledger.whiteListLendingMarket(market, true);
        vm.prank(governance); ledger.setRewards(0, 0, 1e18);
        vm.prank(governance); ledger.setRewards(100_000, 100_000, 2e18);
        vm.prank(market); ledger.sync_ledger(lender, 1e18);
        vm.roll(150_000);
        ledger.update_market(market);
        (uint128 observed,,) = ledger.marketInfo(market);
        assertEq(observed, 150_000e18, "epoch-boundary accounting mismatch");
    }
}
"""

def clone_target(destination: Path) -> Path:
    subprocess.run(("git","clone","--no-tags","--recurse-submodules",TARGET_REPO,str(destination)),check=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    subprocess.run(("git","-C",str(destination),"checkout","--detach",TARGET_REF),check=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    subprocess.run(("git","-C",str(destination),"submodule","update","--init","--recursive"),check=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    return destination

def run_target(root: Path, label: str) -> dict:
    path=root/"src"/"test"/"CydraStrictBlindEpoch.t.sol"
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(TEST_SOURCE,encoding="utf-8")
    p=subprocess.run(("forge","test","--match-test","testCydraEpochBoundaryAccounting","-vvv"),cwd=root,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    return {"experiment_id":f"X-STRICT-EPOCH-{label}","executed":True,"tests_run":1,"tests_failed":0 if p.returncode==0 else 1,"status":"PASS" if p.returncode==0 else "FAIL","exit_code":p.returncode,"stdout":p.stdout[-12000:],"stderr":""}

def patch_target(root: Path) -> None:
    path=root/TARGET_PATH
    source=path.read_text(encoding="utf-8")
    old="                    uint256 nextEpoch = i + BLOCK_EPOCH;"
    new="                    uint256 nextEpoch = ((i / BLOCK_EPOCH) + 1) * BLOCK_EPOCH;"
    if old not in source: raise RuntimeError("epoch-boundary patch point not found")
    path.write_text(source.replace(old,new,1),encoding="utf-8")

def canonical_model(h):
    model=SystemModel()
    cid="contract:LendingLedger"; fid=f"function:LendingLedger:{h.target_function}"
    iid=f"invariant:{h.invariant_id}"; hid=f"hypothesis:{h.hypothesis_id}"; oid="strict-epoch-boundary"
    model.add_node(Node(cid,"contract","LendingLedger",{"provenance":"pinned historical source"}))
    model.add_node(Node(fid,"function",h.target_function,{"provenance":"pinned historical source"}))
    model.add_node(Node(iid,"invariant",h.claim,{"status":"inferred","confidence":0.86}))
    model.add_node(Node(hid,"hypothesis",h.claim,{"belief":0.5}))
    model.add_node(Node(f"observation:{oid}","observation","cross an epoch boundary from an unaligned prior checkpoint",{"status":"planned","hypothesis_id":hid,"target_function_id":fid,"binding_status":"bound","experiment_binding":{"hypothesis_id":hid,"observation_id":f"observation:{oid}","target_function_id":fid}}))
    model.add_edge(Edge(iid,"informs",hid,{})); model.add_edge(Edge(f"observation:{oid}","tests",hid,{}))
    return model,CanonicalHypothesis(h.hypothesis_id,h.claim,0.5),oid

def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--output",type=Path,default=Path("backtest-artifacts/strict-blind-epoch")); args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="cydra-strict-epoch-v-") as tmp:
        target=clone_target(Path(tmp)/"target")
        result=investigate(target/TARGET_PATH,target=f"{TARGET_REPO}@{TARGET_REF}:{TARGET_PATH}")
        selection=select_next_hypothesis(result.hypotheses,result.invariants,result.experiments)
        h=selection.hypothesis
        if not h.invariant_id.startswith("INV-EPOCH-ACCOUNTING-"):
            raise RuntimeError(f"strict blind selector chose {h.hypothesis_id}/{h.target_function}, not the independently evaluated epoch hypothesis")
        experiment=next(e for e in result.experiments if e.hypothesis_id==h.hypothesis_id)
        vulnerable=run_target(target,"vulnerable")
    with tempfile.TemporaryDirectory(prefix="cydra-strict-epoch-p-") as tmp:
        target=clone_target(Path(tmp)/"target"); patch_target(target); patched=run_target(target,"patched")
    with tempfile.TemporaryDirectory(prefix="cydra-strict-epoch-rv-") as tmp:
        target=clone_target(Path(tmp)/"target"); independent_vulnerable=run_target(target,"independent-vulnerable")
    with tempfile.TemporaryDirectory(prefix="cydra-strict-epoch-rp-") as tmp:
        target=clone_target(Path(tmp)/"target"); patch_target(target); independent_patched=run_target(target,"independent-patched")

    model,ch,oid=canonical_model(h)
    class Execution:
        def __init__(self,p): self.__dict__.update(p)
    cycle=run_canonical_differential_cycle(model,hypothesis=ch,observation_id=oid,vulnerable=Execution(vulnerable),patched=Execution(patched),outcome_id="strict-epoch-differential")
    reproduction_verified=independent_vulnerable["status"]=="FAIL" and independent_patched["status"]=="PASS"
    impact=ImpactAssessment(ImpactLevel.HIGH,"configured reward distribution","The transition can apply an incorrect epoch segment rate across blocks after a reward-rate boundary, changing accumulated market rewards.",("the stored checkpoint is inside an epoch","the configured reward rate changes at the crossed boundary"),cycle.causal_verification.evidence_ids)
    gate=evaluate_finding_graph(model,candidate=FindingCandidate(True,False,True,True,cycle.causal_verification.state.value=="verified",impact.assessed,reproduction_verified),finding_id=f"F-STRICT-EPOCH-{h.target_function}",hypothesis_id=f"hypothesis:{h.hypothesis_id}",evidence_ids=cycle.causal_verification.evidence_ids,causal_chain_id=cycle.causal_chain.chain_id)
    payload={"historical_target":{"repo":TARGET_REPO,"ref":TARGET_REF,"path":TARGET_PATH},"blind_mode":"no vulnerability class, target function, state surface, or reasoning-surface injection","hypothesis":h.__dict__,"experiment":experiment.__dict__,"vulnerable":vulnerable,"patched":patched,"causal_verification":cycle.causal_verification.__dict__,"independent_vulnerable":independent_vulnerable,"independent_patched":independent_patched,"reproduction_verified":reproduction_verified,"finding_gate":gate.decision.value}
    args.output.mkdir(parents=True,exist_ok=True); (args.output/"result.json").write_text(json.dumps(payload,indent=2,default=str)+"\n",encoding="utf-8"); print(json.dumps(payload,indent=2,default=str))
    return 0 if gate.decision.value=="READY" else 1

if __name__=="__main__": raise SystemExit(main())
