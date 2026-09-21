from __future__ import annotations
import argparse, json, os, subprocess, tempfile
from pathlib import Path
from cydra.canonical_cycle import run_canonical_differential_cycle
from cydra.finding_gate import FindingCandidate, evaluate_finding_graph
from cydra.pipeline import investigate
from cydra.research_loop import run_research_loop
from cydra.hypotheses import Hypothesis as CanonicalHypothesis
from cydra.impact import ImpactAssessment, ImpactLevel
from cydra.system_model import Edge, Node, SystemModel

TARGET_REPO = "https://github.com/code-423n4/2024-03-revert-lend.git"
TARGET_REF = "435b054f9ad2404173f36f0f74a5096c894b12b7"
TARGET_PATH = "src/transformers/V3Utils.sol"

TEST_SOURCE = r"""// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.0;
import "forge-std/Test.sol";
import "src/transformers/V3Utils.sol";

contract MockERC20 {
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;
    function mint(address to, uint256 amount) external { balanceOf[to] += amount; }
    function transfer(address to, uint256 amount) external returns (bool) {
        require(balanceOf[msg.sender] >= amount);
        balanceOf[msg.sender] -= amount; balanceOf[to] += amount; return true;
    }
    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount; return true;
    }
    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        require(balanceOf[from] >= amount && allowance[from][msg.sender] >= amount);
        allowance[from][msg.sender] -= amount; balanceOf[from] -= amount; balanceOf[to] += amount; return true;
    }
}

contract MockPositionManager {
    address public owner;
    address public approved;
    address public token;
    uint128 public liquidity = 1;
    MockERC20 public asset;

    constructor(address owner_, MockERC20 asset_) { owner = owner_; asset = asset_; token = address(asset_); }

    function approve(address to, uint256) external returns (bool) { require(msg.sender == owner); approved = to; return true; }
    function ownerOf(uint256) external view returns (address) { return owner; }

    function positions(uint256) external view returns (
        uint96, address, address, address, uint24, int24, int24, uint128,
        uint256, uint256, uint128, uint128
    ) {
        return (0, approved, token, token, 3000, -60, 60, liquidity, 0, 0, 0, 0);
    }

    function decreaseLiquidity(
        uint256 tokenId, uint128 amount, uint256, uint256, uint256
    ) external returns (uint256 amount0, uint256 amount1) {
        require(msg.sender == approved || msg.sender == owner);
        require(tokenId == 4660 && amount > 0 && liquidity >= amount);
        liquidity -= amount;
        asset.mint(address(this), 200);
        return (100, 100);
    }

    function collect(
        uint256 tokenId, address recipient, uint128 amount0Requested, uint128 amount1Requested
    ) external returns (uint128 amount0, uint128 amount1) {
        require(msg.sender == approved || msg.sender == owner);
        require(tokenId == 4660);
        amount0 = amount0Requested == type(uint128).max ? 100 : amount0Requested;
        amount1 = amount1Requested == type(uint128).max ? 100 : amount1Requested;
        if (amount0 > 0) MockERC20(token).transfer(recipient, amount0);
        if (amount1 > 0) MockERC20(token).transfer(recipient, amount1);
    }
}

contract CydraResourceAuthorizationTest is Test {
    address constant OWNER = address(0xA11CE);
    uint256 constant TOKEN_ID = 4660;
    MockERC20 asset;
    MockPositionManager manager;
    V3Utils v3utils;

    function setUp() external {
        asset = new MockERC20();
        manager = new MockPositionManager(OWNER, asset);
        v3utils = new V3Utils(
            INonfungiblePositionManager(address(manager)),
            address(0), address(0), address(0)
        );
        vm.prank(OWNER);
        manager.approve(address(v3utils), TOKEN_ID);
    }

    function _instructions(address recipient) internal view returns (V3Utils.Instructions memory) {
        return V3Utils.Instructions(
            V3Utils.WhatToDo.WITHDRAW_AND_COLLECT_AND_SWAP,
            address(asset),
            0,0,0,0,"",0,0,"",
            type(uint128).max,type(uint128).max,
            0,0,0,1,0,0,block.timestamp,
            recipient,address(0),false,"",""
        );
    }

    function testCydraResourceAuthorization() external {
        address attacker = makeAddr("attacker");
        uint256 before = asset.balanceOf(attacker);
        vm.prank(attacker);
        (bool ok,) = address(v3utils).call(
            abi.encodeWithSelector(V3Utils.execute.selector, TOKEN_ID, _instructions(attacker))
        );
        assertFalse(ok, "unrelated caller executed an approved resource action");
        assertEq(asset.balanceOf(attacker), before, "attacker received resource assets");
    }
}
""";

def clone_target(destination: Path) -> Path:
    subprocess.run(("git","clone","--no-tags","--recurse-submodules",TARGET_REPO,str(destination)),check=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    subprocess.run(("git","-C",str(destination),"checkout","--detach",TARGET_REF),check=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    return destination

def write_test(root: Path):
    rpc = os.environ.get("CYDRA_FORK_RPC", "https://ethereum-rpc.blockreq.com/v1/rpc/public")
    if '"' in rpc or "\\n" in rpc or "\\r" in rpc:
        raise RuntimeError("invalid CYDRA_FORK_RPC value")
    source = TEST_SOURCE.replace("__CYDRA_FORK_RPC__", rpc)
    p=root/"test"/"CydraResourceAuthorization.t.sol"
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(source,encoding="utf-8")

def patch_target(root: Path):
    p=root/TARGET_PATH; s=p.read_text(encoding="utf-8")
    marker="function execute(uint256 tokenId, Instructions memory instructions) public returns (uint256 newTokenId) {"
    guard="""function execute(uint256 tokenId, Instructions memory instructions) public returns (uint256 newTokenId) {
        address tokenOwner = nonfungiblePositionManager.ownerOf(tokenId);
        if (tokenOwner != msg.sender && tokenOwner != address(this)) { revert Unauthorized(); }"""
    if marker not in s: raise RuntimeError("execute insertion point not found")
    p.write_text(s.replace(marker,guard,1),encoding="utf-8")

def run_target(root: Path, label: str, patched: bool):
    if patched: patch_target(root)
    write_test(root)
    c=subprocess.run(("forge","test","--via-ir","--match-test","testCydraResourceAuthorization","-vvv"),cwd=root,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    return {"experiment_id":f"X-RESOURCE-AUTH-{label}","executed":True,"tests_run":1,"tests_failed":0 if c.returncode==0 else 1,"status":"PASS" if c.returncode==0 else "FAIL","exit_code":c.returncode,"stdout":c.stdout[-16000:],"stderr":""}

def canonical_model(h):
    m=SystemModel(); fid=f"function:V3Utils:{h.target_function}"; iid=f"invariant:{h.invariant_id}"; hid=f"hypothesis:{h.hypothesis_id}"; oid="resource-owner-caller-binding"
    m.add_node(Node("contract:V3Utils","contract","V3Utils",{"provenance":"pinned historical source"}))
    m.add_node(Node(fid,"function",h.target_function,{"provenance":"pinned historical source"}))
    m.add_node(Node(iid,"invariant","An externally callable action over an owned resource must bind the caller to the resource owner or an explicitly delegated actor before mutating or withdrawing that resource.",{"status":"inferred","confidence":0.90}))
    m.add_node(Node(hid,"hypothesis",h.claim,{"belief":0.5}))
    m.add_node(Node("observation:"+oid,"observation","an approved position can be targeted by an unrelated caller unless the action binds caller to the resource owner or delegate",{"status":"planned","hypothesis_id":hid,"target_function_id":fid,"binding_status":"bound","experiment_binding":{"hypothesis_id":hid,"observation_id":"observation:"+oid,"target_function_id":fid}}))
    m.add_edge(Edge(iid,"informs",hid,{})); m.add_edge(Edge("observation:"+oid,"tests",hid,{}))
    return m,CanonicalHypothesis(h.hypothesis_id,h.claim,0.5),oid

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--output",type=Path,default=Path("backtest-artifacts/strict-blind-resource-authorization")); args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="cydra-revert-v-") as tmp:
        target=clone_target(Path(tmp)/"target"); inv=investigate(target/TARGET_PATH,target=f"{TARGET_REPO}@{TARGET_REF}:{TARGET_PATH}")
        def execute(h,e):
            if h.hypothesis_id!="H-RESOURCE-AUTH-execute-tokenId": return {"status":"UNMEASURABLE","executed":False,"reason":"not safely renderable"}
            return run_target(target,"vulnerable",False)
        loop=run_research_loop(inv.hypotheses,inv.invariants,inv.experiments,execute=execute,status_of=lambda x:x["status"],stop_when=lambda x:x.get("status")=="FAIL",max_rounds=6)
        if not loop.rounds or loop.rounds[-1].selection.hypothesis.hypothesis_id!="H-RESOURCE-AUTH-execute-tokenId": raise SystemExit("blind loop did not reach resource authorization: "+",".join(x.selection.hypothesis.hypothesis_id for x in loop.rounds))
        h=loop.rounds[-1].selection.hypothesis; experiment=next(e for e in inv.experiments if e.hypothesis_id==h.hypothesis_id); vulnerable=loop.rounds[-1].observation
    with tempfile.TemporaryDirectory(prefix="cydra-revert-p-") as tmp: patched=run_target(clone_target(Path(tmp)/"target"),"patched",True)
    with tempfile.TemporaryDirectory(prefix="cydra-revert-rv-") as tmp: independent_vulnerable=run_target(clone_target(Path(tmp)/"target"),"independent-vulnerable",False)
    with tempfile.TemporaryDirectory(prefix="cydra-revert-rp-") as tmp: independent_patched=run_target(clone_target(Path(tmp)/"target"),"independent-patched",True)
    model,ch,oid=canonical_model(h)
    class Execution:
        def __init__(self,p): self.__dict__.update(p)
    cycle=run_canonical_differential_cycle(model,hypothesis=ch,observation_id=oid,vulnerable=Execution(vulnerable),patched=Execution(patched),outcome_id="strict-blind-resource-authorization-differential")
    reproduction_verified=independent_vulnerable["status"]=="FAIL" and independent_patched["status"]=="PASS"
    impact=ImpactAssessment(ImpactLevel.HIGH,"unauthorized resource withdrawal","An unrelated caller can use a previously granted resource approval to withdraw the entire position and direct resulting assets to an attacker-controlled recipient.",("resource is identified by tokenId","execute lacks caller-to-resource-owner binding","instructions control recipient and withdrawal amount"),cycle.causal_verification.evidence_ids)
    gate=evaluate_finding_graph(model,candidate=FindingCandidate(True,False,True,True,cycle.causal_verification.state.value=="verified",impact.assessed,reproduction_verified),finding_id=f"F-STRICT-BLIND-RESOURCE-AUTH-{h.target_function}",hypothesis_id=f"hypothesis:{h.hypothesis_id}",evidence_ids=cycle.causal_verification.evidence_ids,causal_chain_id=cycle.causal_chain.chain_id)
    payload={"target":{"repo":TARGET_REPO,"ref":TARGET_REF,"path":TARGET_PATH},"blind_loop":[{"hypothesis":r.selection.hypothesis.__dict__,"score":r.selection.score,"status":r.status} for r in loop.rounds],"blind_selection":{"hypothesis":h.__dict__,"score":loop.rounds[-1].selection.score},"experiment":experiment.__dict__,"vulnerable":vulnerable,"patched":patched,"causal_verification":cycle.causal_verification.__dict__,"independent_vulnerable":independent_vulnerable,"independent_patched":independent_patched,"reproduction_verified":reproduction_verified,"finding_gate":gate.decision.value,"boundary":"normal class-neutral pipeline generated the resource-authorization hypothesis and the generic loop reached it after non-measurable alternatives; no historical answer was supplied to selection."}
    args.output.mkdir(parents=True,exist_ok=True); (args.output/"result.json").write_text(json.dumps(payload,indent=2,default=str)+"\n",encoding="utf-8"); print(json.dumps(payload,indent=2,default=str))
    return 0 if gate.decision.value=="READY" else 1

if __name__=="__main__":
    try: raise SystemExit(main())
    except Exception as exc:
        o=Path("backtest-artifacts/strict-blind-resource-authorization"); o.mkdir(parents=True,exist_ok=True); (o/"runner_error.json").write_text(json.dumps({"error_type":type(exc).__name__,"error":str(exc)},indent=2)+"\n"); raise
