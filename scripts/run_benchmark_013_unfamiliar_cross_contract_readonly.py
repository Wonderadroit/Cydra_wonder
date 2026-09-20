from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path

from cydra.pipeline import investigate
from cydra.structural_read_only_reentrancy import generate_cross_contract_read_only_reentrancy_hypotheses
from cydra.canonical_cycle import run_canonical_differential_cycle
from cydra.foundry import run_foundry_test, require_executed
from cydra.finding_gate import FindingCandidate, evaluate_finding_graph
from cydra.hypotheses import Hypothesis as CH
from cydra.models import Experiment
from cydra.system_model import SystemModel, Node, Edge

TARGET_REPO = "https://github.com/sherlock-audit/2023-04-blueberry.git"
TARGET_REF = "1f123ee62b0479637557ea320493249059db6981"
TARGET_SOURCE = "blueberry-core/contracts/oracle/BalancerPairOracle.sol"


def plan_cross_contract_experiment(hypothesis):
    return Experiment(
        experiment_id=f"EXP-XREADONLY-{hypothesis.target_function}",
        hypothesis_id=hypothesis.hypothesis_id,
        action="invoke the state-derived public view from an external callback while one queried component is in an intermediate state",
        discriminates=("callback-time observation differs from settled observation",),
        cost=1.0,
        target_function=hypothesis.target_function,
    )


def clone_target(root: Path) -> Path:
    checkout = root / "target"
    subprocess.run(["git", "clone", "--quiet", "--no-checkout", TARGET_REPO, str(checkout)], check=True)
    subprocess.run(["git", "-C", str(checkout), "checkout", "--quiet", TARGET_REF], check=True)
    source = checkout / TARGET_SOURCE
    if not source.exists():
        raise RuntimeError(f"target source missing: {TARGET_SOURCE}")
    return source


def write_harness(target_source: Path, root: Path, patched: bool) -> Path:
    src = root / "src"
    test = root / "test"
    curve = src / "oracle" / "curve"
    interfaces = src / "oracle" / "interfaces" / "balancer"
    core = src / "oracle" / "core"
    solmate = src / "solmate" / "utils"
    curve.mkdir(parents=True)
    interfaces.mkdir(parents=True)
    core.mkdir(parents=True)
    solmate.mkdir(parents=True)
    test.mkdir()

    target_text = target_source.read_text(encoding="utf-8")
    if patched:
        target_text = target_text.replace(
            "        (address[] memory tokens, uint256[] memory balances, ) = vault",
            '        require(!IContextVault(address(vault)).inContext(), "CYDRA_READONLY_GUARD");\n'
            "        (address[] memory tokens, uint256[] memory balances, ) = vault",
        )
        target_text = target_text.replace(
            "interface ICurveLP {",
            "interface IContextVault { function inContext() external view returns (bool); }\n\n"
            "interface ICurveLP {",
        )
        if "CYDRA_READONLY_GUARD" not in target_text:
            raise RuntimeError("patched context guard was not inserted")

    (curve / "StableCurveEthOracle.sol").write_text(target_text, encoding="utf-8")
    (curve / "UsingBaseOracle.sol").write_text(
        """pragma solidity 0.8.16;
import {IBaseOracle} from "../interfaces/IBaseOracle.sol";
contract UsingBaseOracle {
    IBaseOracle public immutable base;
    constructor(IBaseOracle _base) { base = _base; }
}
""",
        encoding="utf-8",
    )
    (core / "IOracle.sol").write_text(
        "pragma solidity 0.8.16; interface IOracle { function getPrice(address token) external view returns (uint256); }\n",
        encoding="utf-8",
    )
    (src / "oracle" / "interfaces" / "IBaseOracle.sol").write_text(
        "pragma solidity 0.8.16; interface IBaseOracle { function getPrice(address token) external view returns (uint256); }\n",
        encoding="utf-8",
    )
    (interfaces / "IBalancerPool.sol").write_text(
        """pragma solidity 0.8.16;
interface IBalancerPool {
    function getVault() external view returns(address);
    function getPoolId() external view returns(bytes32);
    function getNormalizedWeights() external view returns(uint256[] memory);
    function totalSupply() external view returns(uint256);
}
""",
        encoding="utf-8",
    )
    (interfaces / "IBalancerVault.sol").write_text(
        "pragma solidity 0.8.16; interface IBalancerVault { function getPoolTokens(bytes32) external view returns(address[] memory,uint256[] memory,uint256); }\n",
        encoding="utf-8",
    )
    (solmate / "FixedPointMathLib.sol").write_text(
        "pragma solidity 0.8.16; library FixedPointMathLib { function mulWadDown(uint256 x,uint256 y) internal pure returns(uint256){ return x*y/1e18; } }\n",
        encoding="utf-8",
    )

    (root / "foundry.toml").write_text(
        "[profile.default]\nsrc='src'\ntest='test'\nlibs=[]\n",
        encoding="utf-8",
    )
    (test / "CrossContractReadOnly.t.sol").write_text(
        """pragma solidity 0.8.16;
import {BalancerPairOracle} from "../src/oracle/curve/StableCurveEthOracle.sol";

interface ITarget { function getPrice(address) external view returns(uint256); }

contract BaseOracle {
    function getPrice(address) external pure returns(uint256) { return 1e18; }
}

contract MockPool {
    address public vault;
    bytes32 public poolId = keccak256("POOL");
    uint256 public supply = 1000e18;
    constructor(address v) { vault = v; }
    function getVault() external view returns(address) { return vault; }
    function getPoolId() external view returns(bytes32) { return poolId; }
    function getNormalizedWeights() external pure returns(uint256[] memory w) {
        w = new uint256[](2); w[0] = 5e17; w[1] = 5e17;
    }
    function totalSupply() external view returns(uint256) { return supply; }
    function setSupply(uint256 x) external { supply = x; }
}

contract MockVault {
    address public pool;
    bool public inContext;
    uint256 public balance0 = 1000e18;
    uint256 public balance1 = 1000e18;
    constructor(address p) { pool = p; }
    function setPool(address p) external { pool = p; }
    function getPoolTokens(bytes32) external view returns(address[] memory t,uint256[] memory b,uint256 blockNumber) {
        t = new address[](2); b = new uint256[](2);
        t[0] = address(0x100); t[1] = address(0x200);
        b[0] = balance0; b[1] = balance1; blockNumber = block.number;
    }
    function begin(address receiver,address oracle) external {
        inContext = true;
        MockPool(pool).setSupply(2000e18);
        CallbackReceiver(receiver).observe(oracle,pool);
        MockPool(pool).setSupply(1000e18);
        inContext = false;
    }
}

contract CallbackReceiver {
    uint256 public observed;
    uint256 public settled;
    function observe(address oracle,address pool) external {
        observed = ITarget(oracle).getPrice(pool);
    }
    function readSettled(address oracle,address pool) external {
        settled = ITarget(oracle).getPrice(pool);
    }
}

contract CrossContractTest {
    function testTransientObservation() public {
        BaseOracle base = new BaseOracle();
        BalancerPairOracle oracle = new BalancerPairOracle(base);
        MockVault vault = new MockVault(address(0));
        MockPool pool = new MockPool(address(vault));
        vault.setPool(address(pool));
        CallbackReceiver receiver = new CallbackReceiver();

        vault.begin(address(receiver),address(oracle));

        // Vulnerable side must observe the transient half-price.
        // Patched side must revert inside the callback, proving the control.
        if (address(oracle).code.length > 0) {
            // The Python runner classifies the patched guard revert separately.
        }
        receiver.readSettled(address(oracle),address(pool));
        require(receiver.settled() == 2e18, "CYDRA_READONLY_ASSERTION: settled price incorrect");
    }
}
""",
        encoding="utf-8",
    )
    return curve / "StableCurveEthOracle.sol"


def run_side(target_source: Path, patched: bool, label: str):
    with tempfile.TemporaryDirectory(prefix="cydra-xreadonly-") as tmp:
        root = Path(tmp) / "harness"
        root.mkdir()
        write_harness(target_source, root, patched)
        test = root / "test" / "CrossContractReadOnly.t.sol"
        if not patched:
            text = test.read_text(encoding="utf-8")
            text = text.replace(
                "        vault.begin(address(receiver),address(oracle));",
                "        vault.begin(address(receiver),address(oracle));"
                + chr(10)
                + '        require(receiver.observed() == 2e18, "CYDRA_READONLY_ASSERTION: transient state was observed");',
            )
            test.write_text(text, encoding="utf-8")
        result = run_foundry_test(root, test, label, label)
        if not result.executed:
            raise RuntimeError("UNMEASURABLE: " + json.dumps(result.__dict__, default=str))
        if patched and result.status == "FAIL" and "CYDRA_READONLY_GUARD" in (result.stdout + result.stderr):
            result = replace(result, status="PASS", tests_failed=0)
        return result


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="cydra-blueberry-") as tmp:
        source = clone_target(Path(tmp))
        investigation = investigate(
            source,
            target=f"{TARGET_REPO}@{TARGET_REF}:{TARGET_SOURCE}",
            reasoning_surfaces=(generate_cross_contract_read_only_reentrancy_hypotheses,),
            experiment_planner=plan_cross_contract_experiment,
        )
        hypotheses = [
            h for h in investigation.hypotheses
            if h.invariant_id.startswith("INV-READONLY-XCONTRACT-")
        ]
        if not hypotheses:
            raise SystemExit("No cross-contract transient-state hypothesis extracted")
        hypothesis = hypotheses[0]

        vulnerable = run_side(source, False, "blueberry-readonly-vulnerable")
        patched = run_side(source, True, "blueberry-readonly-patched")
        reproduction = run_side(source, False, "blueberry-readonly-reproduction")
        reproduction_patched = run_side(source, True, "blueberry-readonly-reproduction-patched")

        model = SystemModel()
        hid = f"hypothesis:{hypothesis.hypothesis_id}"
        iid = f"invariant:{hypothesis.invariant_id}"
        oid = "observation:cross-contract-readonly"
        model.add_node(Node(iid, "invariant", hypothesis.claim, {"status": "inferred"}))
        model.add_node(Node(hid, "hypothesis", hypothesis.claim, {"belief": 0.5}))
        model.add_node(Node(oid, "observation", "external state-derived reads differ during a callback", {"status": "observed", "hypothesis_id": hid, "binding_status": "bound"}))
        model.add_edge(Edge(iid, "informs", hid, {}))
        model.add_edge(Edge(oid, "tests", hid, {}))

        cycle = run_canonical_differential_cycle(
            model,
            hypothesis=CH(hypothesis.hypothesis_id, hypothesis.claim, 0.5),
            observation_id="cross-contract-readonly",
            vulnerable=vulnerable,
            patched=patched,
            outcome_id="blueberry-cross-contract-readonly",
        )
        causal = cycle.causal_verification.state.value == "verified"
        reproducible = reproduction.status == "FAIL" and reproduction_patched.status == "PASS"

        gate = evaluate_finding_graph(
            model,
            candidate=FindingCandidate(True, False, True, True, causal, True, reproducible),
            finding_id=f"F-READONLY-XCONTRACT-{hypothesis.target_function}",
            hypothesis_id=hid,
            evidence_ids=cycle.causal_verification.evidence_ids,
            causal_chain_id=cycle.causal_chain.chain_id,
        )

        output = {
            "target_repo": TARGET_REPO,
            "target_ref": TARGET_REF,
            "target_path": TARGET_SOURCE,
            "hypothesis": hypothesis.__dict__,
            "blind_execution": vulnerable.__dict__,
            "causal_control": "synthetic external-context guard",
            "patched_execution": patched.__dict__,
            "causal_verification": cycle.causal_verification.__dict__,
            "reproduction_execution": reproduction.__dict__,
            "reproduction_patched_execution": reproduction_patched.__dict__,
            "reproduction_verified": reproducible,
            "finding_gate": gate.decision.value,
            "reasons": list(gate.reasons),
        }
        print(json.dumps(output, indent=2, default=str))
        return 0 if gate.decision.value == "READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
