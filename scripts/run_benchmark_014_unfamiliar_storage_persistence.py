from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from cydra.canonical_cycle import run_canonical_differential_cycle
from cydra.foundry import require_executed, run_foundry_test, test_path_for
from cydra.finding_gate import FindingCandidate, evaluate_finding_graph
from cydra.hypotheses import Hypothesis as CanonicalHypothesis
from cydra.impact import ImpactAssessment, ImpactLevel
from cydra.models import Experiment
from cydra.pipeline import investigate
from cydra.solidity_model import parse_solidity
from cydra.storage_persistence_execution import generate_storage_persistence_test
from cydra.structural_storage_persistence import generate_storage_persistence_hypotheses
from cydra.system_model import Edge, Node, SystemModel

TARGET_REPO = "https://github.com/sherlock-audit/2024-04-titles.git"
TARGET_REF = "d7f60952df22da00b772db5d3a8272a988546089"
TARGET_SOURCE = "wallflower-contract-v2/src/graph/TitlesGraph.sol"


def _clone(root: Path) -> Path:
    checkout = root / "target"
    subprocess.run(["git", "clone", "--quiet", "--no-tags", "--no-checkout", TARGET_REPO, str(checkout)], check=True)
    subprocess.run(["git", "-C", str(checkout), "checkout", "--quiet", TARGET_REF], check=True)
    source = checkout / TARGET_SOURCE
    if not source.exists():
        raise RuntimeError("historical target source missing")
    return source


def _write_harness(target: Path, root: Path, patched: bool) -> Path:
    src = root / "src"
    lib = root / "lib"
    test = root / "test"
    for p in (
        src / "graph", src / "interfaces", src / "shared",
        lib / "solady/src/auth", lib / "solady/src/utils",
        lib / "openzeppelin-contracts/contracts/utils/structs",
        test,
    ):
        p.mkdir(parents=True, exist_ok=True)

    text = target.read_text(encoding="utf-8")
    if patched:
        old = """function _setAcknowledged(bytes32 edgeId_, bytes calldata data_, bool acknowledged_)
        internal
        returns (Edge memory edge)"""
        new = """function _setAcknowledged(bytes32 edgeId_, bytes calldata data_, bool acknowledged_)
        internal
        returns (Edge storage edge)"""
        if old not in text:
            raise RuntimeError("storage causal control anchor missing")
        text = text.replace(old, new, 1)

    (src / "graph/TitlesGraph.sol").write_text(text, encoding="utf-8")
    (src / "shared/Common.sol").write_text(
        """pragma solidity ^0.8.24;
uint256 constant ADMIN_ROLE = 1;
error Unauthorized();
enum NodeType { ACCOUNT, COLLECTION_ERC721, COLLECTION_ERC1155, TOKEN_ERC721, TOKEN_ERC1155, TOKEN_ERC20 }
struct Target { uint256 chainId; address target; }
struct Node { NodeType nodeType; Target entity; Target creator; bytes data; }
struct Edge { Node from; Node to; bool acknowledged; bytes data; }
""",
        encoding="utf-8",
    )
    (src / "interfaces/IOpenGraph.sol").write_text(
        """pragma solidity ^0.8.24;
import {Node, Edge} from "src/shared/Common.sol";
interface IOpenGraph {
    event NodeTouched(Node node, bytes data);\n    event EdgeCreated(Edge edge, bytes data);\n    function createEdge(Node memory, Node memory, bytes calldata) external returns (Edge memory);
}
""",
        encoding="utf-8",
    )
    (src / "interfaces/IEdgeManager.sol").write_text(
        """pragma solidity ^0.8.24;
import {Edge} from "src/shared/Common.sol";
interface IEdgeManager {
    event EdgeAcknowledged(Edge edge, address indexed actor, bytes data);
    event EdgeUnacknowledged(Edge edge, address indexed actor, bytes data);
    function acknowledgeEdge(bytes32, bytes calldata) external returns (Edge memory);
    function acknowledgeEdge(bytes32, bytes calldata, bytes calldata) external returns (Edge memory);
    function unacknowledgeEdge(bytes32, bytes calldata) external returns (Edge memory);
    function unacknowledgeEdge(bytes32, bytes calldata, bytes calldata) external returns (Edge memory);
}
""",
        encoding="utf-8",
    )
    (lib / "openzeppelin-contracts/contracts/utils/structs/EnumerableSet.sol").write_text(
        """pragma solidity ^0.8.24;
library EnumerableSet {
    struct Bytes32Set { mapping(bytes32 => bool) present; }
    function add(Bytes32Set storage s, bytes32 v) internal returns (bool) {
        if (s.present[v]) return false;
        s.present[v] = true;
        return true;
    }
    function contains(Bytes32Set storage s, bytes32 v) internal view returns (bool) { return s.present[v]; }
}
""",
        encoding="utf-8",
    )
    (lib / "solady/src/auth/OwnableRoles.sol").write_text(
        """pragma solidity ^0.8.24;
abstract contract OwnableRoles {
    address internal _owner;
    mapping(address => uint256) internal _roles;
    function _initializeOwner(address owner_) internal { _owner = owner_; }
    function _grantRoles(address guy, uint256 roles) internal { _roles[guy] |= roles; }
    function _removeRoles(address guy, uint256 roles) internal { _roles[guy] &= ~roles; }
    function grantRoles(address guy, uint256 roles) public payable virtual { _grantRoles(guy, roles); }
    function revokeRoles(address guy, uint256 roles) public payable virtual { _removeRoles(guy, roles); }
    modifier onlyOwnerOrRoles(uint256 role) { require(msg.sender == _owner || (_roles[msg.sender] & role) != 0); _; }
    modifier onlyRolesOrOwner(uint256 role) { require(msg.sender == _owner || (_roles[msg.sender] & role) != 0); _; }
}
""",
        encoding="utf-8",
    )
    (lib / "solady/src/utils/EIP712.sol").write_text(
        """pragma solidity ^0.8.24;
abstract contract EIP712 {
    bytes32 internal constant _DOMAIN_TYPEHASH =
        keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)");
    function _hashTypedData(bytes32 digest) internal view returns (bytes32) {
        return keccak256(abi.encode(_DOMAIN_TYPEHASH, digest, block.chainid, address(this)));
    }
    function _domainNameAndVersion() internal pure virtual returns (string memory, string memory);
}
""",
        encoding="utf-8",
    )
    (lib / "solady/src/utils/SignatureCheckerLib.sol").write_text(
        """pragma solidity ^0.8.24;
library SignatureCheckerLib {
    function isValidSignatureNowCalldata(address, bytes32, bytes calldata) internal pure returns (bool) {
        return true;
    }
}
""",
        encoding="utf-8",
    )
    (lib / "solady/src/utils/UUPSUpgradeable.sol").write_text(
        """pragma solidity ^0.8.24;
abstract contract UUPSUpgradeable {
    function _authorizeUpgrade(address) internal view virtual;
}
""",
        encoding="utf-8",
    )
    (root / "foundry.toml").write_text(
        "[profile.default]\nsrc='src'\ntest='test'\nlibs=['lib']\nremappings=['src/=src/','lib/=lib/']\n",
        encoding="utf-8",
    )

    contract = parse_solidity(src / "graph/TitlesGraph.sol")[0]
    contribution = generate_storage_persistence_hypotheses(contract)
    if not contribution.hypotheses:
        raise RuntimeError("storage-persistence reasoning did not find the target mechanism")
    hypothesis = contribution.hypotheses[0]
    experiment = Experiment(
        "EXP-STORAGE-PERSISTENCE-" + hypothesis.target_function,
        hypothesis.hypothesis_id,
        "invoke the successful state transition and inspect the same storage element after the call",
        ("persistent state changes",),
        1.0,
        target_function=hypothesis.target_function,
    )
    out = test_path_for(root, "generated/storage-persistence.t.sol")
    return generate_storage_persistence_test(
        hypothesis,
        contract,
        "../../src/graph/TitlesGraph.sol",
        "TitlesGraph",
        out,
        experiment=experiment,
    )


def _run_side(target: Path, patched: bool, label: str):
    with tempfile.TemporaryDirectory(prefix="cydra-storage-") as tmp:
        root = Path(tmp) / "project"
        test = _write_harness(target, root, patched)
        result = run_foundry_test(root, test, label, label)
        if not result.executed:
            print(json.dumps({"foundry_diagnostic": result.__dict__}, indent=2, default=str))
        require_executed(result)
        return result


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="cydra-target-") as tmp:
        target = _clone(Path(tmp))
        result = investigate(
            target,
            target=f"{TARGET_REPO}@{TARGET_REF}:{TARGET_SOURCE}",
            reasoning_surfaces=(generate_storage_persistence_hypotheses,),
            experiment_planner=lambda h: Experiment(
                "EXP-STORAGE-PERSISTENCE-" + h.target_function,
                h.hypothesis_id,
                "invoke the successful state transition and inspect the same storage element after the call",
                ("persistent state changes",),
                1.0,
                target_function=h.target_function,
            ),
        )
        hypotheses = [h for h in result.hypotheses if h.invariant_id.startswith("INV-STORAGE-PERSISTENCE-")]
        if not hypotheses:
            raise SystemExit("No blind storage-persistence hypothesis extracted")
        hypothesis = hypotheses[0]
        experiment = next(e for e in result.experiments if e.hypothesis_id == hypothesis.hypothesis_id)

        vulnerable = _run_side(target, False, "vulnerable")
        patched = _run_side(target, True, "patched")

        contract = result.contracts[0]
        model = SystemModel()
        hid = f"hypothesis:{hypothesis.hypothesis_id}"
        iid = f"invariant:{hypothesis.invariant_id}"
        fid = f"function:{contract.name}:{hypothesis.target_function}"
        oid = "storage-persistence"
        model.add_node(Node(fid, "function", hypothesis.target_function, {}))
        model.add_node(Node(iid, "invariant", hypothesis.claim, {"status": "inferred"}))
        model.add_node(Node(hid, "hypothesis", hypothesis.claim, {"belief": 0.5}))
        model.add_node(Node(f"observation:{oid}", "observation", "post-call storage state", {
            "status": "planned",
            "hypothesis_id": hid,
            "target_function_id": fid,
            "binding_status": "bound",
            "experiment_binding": {
                "hypothesis_id": hid,
                "observation_id": f"observation:{oid}",
                "target_function_id": fid,
            },
        }))
        model.add_edge(Edge(iid, "informs", hid, {}))
        model.add_edge(Edge(f"observation:{oid}", "tests", hid, {}))

        cycle = run_canonical_differential_cycle(
            model,
            hypothesis=CanonicalHypothesis(hypothesis.hypothesis_id, hypothesis.claim, 0.5),
            observation_id=oid,
            vulnerable=vulnerable,
            patched=patched,
            outcome_id="storage-persistence-differential",
        )

        with tempfile.TemporaryDirectory(prefix="cydra-repro-v-") as tmp2:
            reproduction = _run_side(target, False, "reproduction")
        with tempfile.TemporaryDirectory(prefix="cydra-repro-p-") as tmp2:
            reproduction_patched = _run_side(target, True, "reproduction-patched")

        reproduction_verified = (
            reproduction.status == "FAIL" and reproduction_patched.status == "PASS"
        )
        impact = ImpactAssessment(
            ImpactLevel.MEDIUM,
            "state transition does not persist",
            "The successful operation leaves the modeled persistent state unchanged.",
            "caller can reach the public state-changing operation",
            cycle.causal_verification.evidence_ids,
        )
        gate = evaluate_finding_graph(
            model,
            candidate=FindingCandidate(
                True,
                False,
                True,
                True,
                cycle.causal_verification.state.value == "verified",
                impact.assessed,
                reproduction_verified,
            ),
            finding_id=f"F-STORAGE-PERSISTENCE-{hypothesis.target_function}",
            hypothesis_id=hid,
            evidence_ids=cycle.causal_verification.evidence_ids,
            causal_chain_id=cycle.causal_chain.chain_id,
        )
        payload = {
            "target": f"{TARGET_REPO}@{TARGET_REF}:{TARGET_SOURCE}",
            "blind_hypothesis": hypothesis.__dict__,
            "experiment": experiment.__dict__,
            "blind_execution": vulnerable.__dict__,
            "patched_execution": patched.__dict__,
            "causal_verification": cycle.causal_verification.__dict__,
            "reproduction_execution": reproduction.__dict__,
            "reproduction_patched_execution": reproduction_patched.__dict__,
            "reproduction_verified": reproduction_verified,
            "finding_gate": gate.decision.value,
            "reasons": list(gate.reasons),
        }
        print(json.dumps(payload, indent=2, default=str))
        return 0 if gate.decision.value == "READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
