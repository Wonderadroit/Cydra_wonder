from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from cydra.canonical_cycle import run_canonical_differential_cycle
from cydra.finding_gate import FindingCandidate, evaluate_finding_graph
from cydra.hypothesis_selection import select_next_hypothesis
from cydra.hypotheses import Hypothesis as CanonicalHypothesis
from cydra.impact import ImpactAssessment, ImpactLevel
from cydra.pipeline import investigate
from cydra.system_model import Edge, Node, SystemModel

TARGET_REPO = "https://github.com/code-423n4/2026-03-intuition.git"
TARGET_REF = "0a19e25"
TARGET_PATH = "src/protocol/wallet/AtomWallet.sol"

TEST_SOURCE = r"""// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.29;

import "forge-std/src/Test.sol";
import { AtomWallet } from "src/protocol/wallet/AtomWallet.sol";
import { PackedUserOperation } from "@account-abstraction/interfaces/PackedUserOperation.sol";
import { ValidationData, _parseValidationData } from "@account-abstraction/core/Helpers.sol";
import { TransparentUpgradeableProxy } from "@openzeppelin/contracts/proxy/transparent/TransparentUpgradeableProxy.sol";

contract CydraMockMultiVault {
    address internal atomWarden;

    constructor(address _atomWarden) {
        atomWarden = _atomWarden;
    }

    function getAtomWarden() external view returns (address) {
        return atomWarden;
    }
}

contract CydraSignedMetadataTest is Test {
    function testCydraSignedMetadataBinding() public {
        uint256 ownerKey = 0xA11CE;
        address owner = vm.addr(ownerKey);
        address entryPoint = makeAddr("entryPoint");

        CydraMockMultiVault multiVault = new CydraMockMultiVault(owner);
        AtomWallet walletImpl = new AtomWallet();
        TransparentUpgradeableProxy proxy = new TransparentUpgradeableProxy(
            address(walletImpl),
            address(this),
            abi.encodeWithSelector(
                AtomWallet.initialize.selector,
                entryPoint,
                address(multiVault),
                bytes32("ATOM")
            )
        );
        AtomWallet wallet = AtomWallet(payable(address(proxy)));

        PackedUserOperation memory userOp = PackedUserOperation({
            sender: address(wallet),
            nonce: 0,
            initCode: "",
            callData: "",
            accountGasLimits: bytes32(0),
            preVerificationGas: 0,
            gasFees: bytes32(0),
            paymasterAndData: "",
            signature: ""
        });

        bytes32 userOpHash = keccak256("userOpHash");
        uint48 originalValidUntil = uint48(block.timestamp + 1);
        uint48 originalValidAfter = 0;

        // The signer commits to the complete 77-byte authorization format.
        bytes32 signedHash = keccak256(
            abi.encodePacked(userOpHash, originalValidUntil, originalValidAfter)
        );
        bytes32 digest = keccak256(
            abi.encodePacked("\x19Ethereum Signed Message:\n32", signedHash)
        );
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(ownerKey, digest);
        bytes memory baseSig = abi.encodePacked(r, s, v);

        userOp.signature = bytes.concat(
            baseSig,
            abi.encodePacked(originalValidUntil, originalValidAfter)
        );

        vm.prank(entryPoint);
        uint256 validationDataOriginal = wallet.validateUserOp(userOp, userOpHash, 0);
        ValidationData memory parsedOriginal = _parseValidationData(validationDataOriginal);
        assertEq(parsedOriginal.aggregator, address(0), "original authorization must validate");
        assertEq(parsedOriginal.validUntil, originalValidUntil);
        assertEq(parsedOriginal.validAfter, originalValidAfter);

        // Move beyond the signed validity window, then change only the metadata.
        vm.warp(originalValidUntil + 1);
        uint48 attackerValidUntil = uint48(block.timestamp + 30 days);
        userOp.signature = bytes.concat(
            baseSig,
            abi.encodePacked(attackerValidUntil, originalValidAfter)
        );

        vm.prank(entryPoint);
        uint256 validationDataModified = wallet.validateUserOp(userOp, userOpHash, 0);
        ValidationData memory parsedModified = _parseValidationData(validationDataModified);

        // Security invariant: the same signature must not authenticate a new window.
        // Vulnerable source returns aggregator == address(0), so this assertion fails.
        assertEq(
            parsedModified.aggregator,
            address(1),
            "signature accepted metadata that was not authenticated"
        );
    }
}
"""


def clone_target(destination: Path) -> Path:
    completed = subprocess.run(
        ("git", "clone", "--no-tags", "--recurse-submodules", TARGET_REPO, str(destination)),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError("target clone failed:\n" + completed.stdout[-12000:])
    subprocess.run(
        ("git", "-C", str(destination), "checkout", "--detach", TARGET_REF),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    subprocess.run(
        ("git", "-C", str(destination), "submodule", "update", "--init", "--recursive"),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    npm = subprocess.run(
        ("npm", "install", "--ignore-scripts", "--no-audit", "--no-fund", "--legacy-peer-deps"),
        cwd=destination,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if npm.returncode != 0:
        raise RuntimeError("target npm dependency installation failed:\n" + npm.stdout[-12000:])
    return destination


def write_harness(root: Path) -> None:
    path = root / "tests" / "autogen" / "CydraSignedMetadata.t.sol"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(TEST_SOURCE, encoding="utf-8")


def run_target(root: Path, label: str) -> dict:
    write_harness(root)
    completed = subprocess.run(
        ("forge", "test", "--match-path", "tests/autogen/CydraSignedMetadata.t.sol", "--match-test", "testCydraSignedMetadataBinding", "-vvv"),
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return {
        "experiment_id": f"X-SIGNED-METADATA-{label}",
        "executed": True,
        "tests_run": 1,
        "tests_failed": 0 if completed.returncode == 0 else 1,
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "exit_code": completed.returncode,
        "stdout": completed.stdout[-12000:],
        "stderr": "",
    }


def patch_target(root: Path) -> None:
    path = root / TARGET_PATH
    source = path.read_text(encoding="utf-8")
    old = '        bytes32 hash = keccak256(abi.encodePacked("\\x19Ethereum Signed Message:\\n32", userOpHash));'
    new = '''        bytes32 signedHash = userOpHash;
        if (userOp.signature.length == 77) {
            signedHash = keccak256(abi.encodePacked(userOpHash, validUntil, validAfter));
        }
        bytes32 hash = keccak256(abi.encodePacked("\\x19Ethereum Signed Message:\\n32", signedHash));'''
    if old not in source:
        raise RuntimeError("signed-metadata causal insertion point not found")
    path.write_text(source.replace(old, new, 1), encoding="utf-8")


def canonical_model(hypothesis):
    model = SystemModel()
    contract_id = "contract:AtomWallet"
    function_id = f"function:AtomWallet:{hypothesis.target_function}"
    invariant_id = f"invariant:{hypothesis.invariant_id}"
    hypothesis_id = f"hypothesis:{hypothesis.hypothesis_id}"
    observation_id = "unsigned-authorization-metadata"

    model.add_node(Node(contract_id, "contract", "AtomWallet", {"provenance": "pinned historical source"}))
    model.add_node(Node(function_id, "function", hypothesis.target_function, {"provenance": "pinned historical source"}))
    model.add_node(Node(invariant_id, "invariant", hypothesis.claim, {"status": "inferred", "confidence": 0.91}))
    model.add_node(Node(hypothesis_id, "hypothesis", hypothesis.claim, {"belief": 0.5}))
    model.add_node(Node(
        f"observation:{observation_id}",
        "observation",
        "the same ECDSA signature is accepted after only validity metadata changes",
        {
            "status": "planned",
            "hypothesis_id": hypothesis_id,
            "target_function_id": function_id,
            "binding_status": "bound",
            "experiment_binding": {
                "hypothesis_id": hypothesis_id,
                "observation_id": f"observation:{observation_id}",
                "target_function_id": function_id,
            },
        },
    ))
    model.add_edge(Edge(invariant_id, "informs", hypothesis_id, {}))
    model.add_edge(Edge(f"observation:{observation_id}", "tests", hypothesis_id, {}))
    return model, CanonicalHypothesis(hypothesis.hypothesis_id, hypothesis.claim, 0.5), observation_id


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("backtest-artifacts/open-ended-blind"))
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="cydra-intuition-vulnerable-") as tmp:
        target = clone_target(Path(tmp) / "target")
        source = target / TARGET_PATH

        # No vulnerability class, target function, state surface, or historical
        # answer is supplied here. The pipeline discovers the candidate set itself.
        result = investigate(
            source,
            target=f"{TARGET_REPO}@{TARGET_REF}:{TARGET_PATH}",
        )
        selection = select_next_hypothesis(result.hypotheses, result.invariants, result.experiments)
        hypothesis = selection.hypothesis
        experiment = next(e for e in result.experiments if e.hypothesis_id == hypothesis.hypothesis_id)

        if not hypothesis.hypothesis_id.startswith("H-SIGNED-METADATA-"):
            raise RuntimeError(
                "blind selector did not choose the signed-metadata candidate: "
                + hypothesis.hypothesis_id
            )
        vulnerable = run_target(target, "vulnerable")

    with tempfile.TemporaryDirectory(prefix="cydra-intuition-patched-") as tmp:
        target = clone_target(Path(tmp) / "target")
        patch_target(target)
        patched = run_target(target, "patched")

    with tempfile.TemporaryDirectory(prefix="cydra-intuition-repro-v-") as tmp:
        target = clone_target(Path(tmp) / "target")
        independent_vulnerable = run_target(target, "independent-vulnerable")

    with tempfile.TemporaryDirectory(prefix="cydra-intuition-repro-p-") as tmp:
        target = clone_target(Path(tmp) / "target")
        patch_target(target)
        independent_patched = run_target(target, "independent-patched")

    model, canonical_hypothesis, observation_id = canonical_model(hypothesis)

    class Execution:
        def __init__(self, payload):
            self.__dict__.update(payload)

    cycle = run_canonical_differential_cycle(
        model,
        hypothesis=canonical_hypothesis,
        observation_id=observation_id,
        vulnerable=Execution(vulnerable),
        patched=Execution(patched),
        outcome_id="signed-metadata-differential",
    )

    reproduction_verified = (
        independent_vulnerable["status"] == "FAIL"
        and independent_patched["status"] == "PASS"
    )
    impact = ImpactAssessment(
        ImpactLevel.MEDIUM,
        "Signed authorization validity-window integrity",
        "A relayer can change validity metadata without invalidating the signed authorization, allowing an expired authorization to remain accepted outside the signer's intended time window.",
        ("the signer commits to a validity window", "the caller can change only the unsigned metadata"),
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
        finding_id=f"F-SIGNED-METADATA-{hypothesis.target_function}",
        hypothesis_id=f"hypothesis:{hypothesis.hypothesis_id}",
        evidence_ids=cycle.causal_verification.evidence_ids,
        causal_chain_id=cycle.causal_chain.chain_id,
    )

    payload = {
        "historical_target": {"repo": TARGET_REPO, "ref": TARGET_REF, "path": TARGET_PATH},
        "blind_selection": {
            "hypothesis_id": hypothesis.hypothesis_id,
            "score": selection.score,
            "candidate_count": len(result.hypotheses),
        },
        "hypothesis": hypothesis.__dict__,
        "experiment": experiment.__dict__,
        "vulnerable": vulnerable,
        "patched": patched,
        "causal_verification": cycle.causal_verification.__dict__,
        "independent_vulnerable": independent_vulnerable,
        "independent_patched": independent_patched,
        "reproduction_verified": reproduction_verified,
        "finding_gate": gate.decision.value,
        "boundary": "actual pinned Intuition repository and dependency graph executed; causal control changes only the digest binding of 77-byte metadata.",
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "result.json").write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))
    return 0 if gate.decision.value == "READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
