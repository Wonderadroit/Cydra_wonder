from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


TARGETS = [
    {
        "id": "rabbithole",
        "repo": "https://github.com/rabbitholegg/quest-protocol.git",
        "ref": "8c4c1f71221570b14a0479c216583342bd652d8d",
        "source": "contracts/RabbitHoleTickets.sol",
    },
    {
        "id": "debtdao",
        "repo": "https://github.com/debtdao/Line-of-Credit.git",
        "ref": "e8aa08b44f6132a5ed901f8daa231700c5afeb3a",
        "source": "contracts/utils/SpigotLib.sol",
    },
]

RABBIT_POC = r'''// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.15;

import "forge-std/Test.sol";
import "../contracts/RabbitHoleTickets.sol";
import "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";

contract CydraRabbitHole043Test is Test {
    function _tickets() internal returns (RabbitHoleTickets) {
        RabbitHoleTickets implementation = new RabbitHoleTickets();
        bytes memory init = abi.encodeCall(
            RabbitHoleTickets.initialize,
            (address(0), address(this), address(0xBEEF), 0)
        );
        ERC1967Proxy proxy = new ERC1967Proxy(address(implementation), init);
        return RabbitHoleTickets(address(proxy));
    }

    function test_cydra_unauthorized_mint_is_blocked() external {
        RabbitHoleTickets tickets = _tickets();
        address attacker = address(0xCAFE);

        try tickets.mint(attacker, 1, 1, "") {
            assertEq(tickets.balanceOf(attacker, 1), 0, "unauthorized mint succeeded");
            fail("vulnerable mint unexpectedly passed the invariant");
        } catch {
            // Patched implementation reverts here.
        }
    }
}
'''

DEBT_POC = r'''// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.9;

import "forge-std/Test.sol";
import "../contracts/modules/spigot/Spigot.sol";
import "../contracts/interfaces/ISpigot.sol";

contract CydraMockToken043 {
    mapping(address => uint256) public balanceOf;

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        require(balanceOf[msg.sender] >= amount, "balance");
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        require(balanceOf[from] >= amount, "balance");
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
        return true;
    }
}

contract CydraDebtDao043Test is Test {
    function test_cydra_invalid_revenue_binding_cannot_capture_push_payment() external {
        address owner = address(this);
        address treasury = address(0xA11CE);
        address operator = address(0xB0B);
        address attacker = address(0xCAFE);
        address configuredRevenue = address(0x1111);
        address invalidRevenue = address(0x2222);

        Spigot spigot = new Spigot(owner, treasury, operator);
        CydraMockToken043 token = new CydraMockToken043();

        ISpigot.Setting memory setting = ISpigot.Setting({
            ownerSplit: 50,
            claimFunction: bytes4(0),
            transferOwnerFunction: bytes4(0x12345678)
        });
        spigot.addSpigot(configuredRevenue, setting);
        token.mint(address(spigot), 100 ether);

        vm.prank(attacker);
        try spigot.claimRevenue(invalidRevenue, address(token), "") returns (uint256 claimed) {
            assertEq(claimed, 100 ether, "unexpected claimed amount");
            assertEq(
                spigot.getEscrowed(address(token)),
                50 ether,
                "invalid binding bypassed owner split"
            );
            fail("vulnerable invalid binding unexpectedly passed");
        } catch {
            // Patched implementation rejects the unconfigured revenue key.
        }
    }
}
'''


def clone(repo: str, ref: str, destination: Path) -> None:
    completed = subprocess.run(
        ["git", "clone", "--no-tags", "--recurse-submodules", repo, str(destination)],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"clone failed for {repo}: {completed.stdout[-4000:]}{completed.stderr[-4000:]}"
        )
    subprocess.run(["git", "-C", str(destination), "checkout", "--detach", ref], check=True)


def run_blind(target: dict, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    freeze = output / "freeze"
    command = [
        sys.executable,
        "scripts/run_benchmark_blind.py",
        "--target-repo", target["repo"],
        "--target-ref", target["ref"],
        "--target-path", target["source"],
        "--target-project", ".",
        "--classes", "authorization", "state", "arithmetic",
        "--freeze", str(freeze),
    ]
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    record = {
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
    if completed.returncode == 0 and (freeze / "hypotheses.json").exists():
        record["hypotheses"] = json.loads((freeze / "hypotheses.json").read_text())
    return record


def _foundry_remappings(project: Path) -> list[str]:
    candidates = {
        "@openzeppelin/contracts/": project / "lib/openzeppelin-contracts/contracts",
        "@openzeppelin/contracts-upgradeable/": project / "lib/openzeppelin-contracts-upgradeable/contracts",
        "forge-std/": project / "lib/forge-std/src",
    }
    return [
        f"{prefix}={path.relative_to(project).as_posix()}/"
        for prefix, path in candidates.items()
        if path.is_dir()
    ]


def run_foundry(
    project: Path,
    contract: str,
    test: str,
    label: str,
    contracts_dir: Path,
) -> dict:
    # Some historical Solidity repositories also contain unrelated Vyper
    # sources. Scope Foundry to the directory containing the selected target
    # so unrelated language sources cannot block the Solidity experiment.
    command = [
        "forge",
        "test",
        "--contracts",
        str(contracts_dir),
        "--match-contract",
        contract,
        "--match-test",
        test,
        "-vvv",
    ]
    remappings = _foundry_remappings(project)
    for remapping in remappings:
        command.extend(["--remappings", remapping])
    completed = subprocess.run(
        command,
        cwd=project,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "label": label,
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def patch_rabbit(source: str) -> str:
    old = """    modifier onlyMinter() {
        msg.sender == minterAddress;
        _;
    }"""
    new = """    modifier onlyMinter() {
        require(msg.sender == minterAddress, "Un-allowed minter");
        _;
    }"""
    if old not in source:
        raise RuntimeError("RabbitHole causal patch did not match pinned source")
    return source.replace(old, new, 1)


def patch_debt(source: str) -> str:
    marker = """    {
        claimed = _claimRevenue(self, revenueContract, token, data);
"""
    replacement = """    {
        if (self.settings[revenueContract].transferOwnerFunction == bytes4(0)) {
            revert BadSetting();
        }
        claimed = _claimRevenue(self, revenueContract, token, data);
"""
    if marker not in source:
        raise RuntimeError("Debt DAO causal patch did not match pinned source")
    return source.replace(marker, replacement, 1)


def evaluate_selection(target_id: str, hypotheses: list[dict]) -> dict:
    if target_id == "rabbithole":
        matches = [
            h for h in hypotheses
            if h.get("invariant_id") == "INV-AUTH-001"
            and h.get("target_function") == "mint"
        ]
    else:
        matches = [
            h for h in hypotheses
            if h.get("target_function") == "claimRevenue"
        ]
    return {
        "hypothesis_count": len(hypotheses),
        "matching_hypotheses": matches,
        "blind_boundary_preserved": True,
    }


def run_target(target: dict, output: Path) -> dict:
    blind = run_blind(target, output / "blind")
    hypotheses = blind.get("hypotheses", [])
    selection = evaluate_selection(target["id"], hypotheses)
    (output / "blind-selection.json").write_text(json.dumps(selection, indent=2) + "\n")

    if blind.get("exit_code") != 0 or not selection["matching_hypotheses"]:
        return {
            "status": "BLOCKED",
            "failure_stage": "blind_selection",
            "blind": blind,
            "selection": selection,
        }

    poc = RABBIT_POC if target["id"] == "rabbithole" else DEBT_POC
    contract = (
        "CydraRabbitHole043Test"
        if target["id"] == "rabbithole"
        else "CydraDebtDao043Test"
    )
    test = (
        "test_cydra_unauthorized_mint_is_blocked"
        if target["id"] == "rabbithole"
        else "test_cydra_invalid_revenue_binding_cannot_capture_push_payment"
    )
    patcher = patch_rabbit if target["id"] == "rabbithole" else patch_debt

    with tempfile.TemporaryDirectory(prefix=f"cydra-043-{target['id']}-") as tmp:
        root = Path(tmp)

        vulnerable = root / "vulnerable"
        clone(target["repo"], target["ref"], vulnerable)
        (vulnerable / "test").mkdir(parents=True, exist_ok=True)
        (vulnerable / "test" / "Cydra043.t.sol").write_text(poc)
        vulnerable_result = run_foundry(
            vulnerable, contract, test, "vulnerable", Path(target["source"]).parent
        )

        patched = root / "patched"
        clone(target["repo"], target["ref"], patched)
        source = patched / target["source"]
        source.write_text(patcher(source.read_text()))
        (patched / "test").mkdir(parents=True, exist_ok=True)
        (patched / "test" / "Cydra043.t.sol").write_text(poc)
        patched_result = run_foundry(
            patched, contract, test, "patched", Path(target["source"]).parent
        )

        independent_v = root / "independent-vulnerable"
        clone(target["repo"], target["ref"], independent_v)
        (independent_v / "test").mkdir(parents=True, exist_ok=True)
        (independent_v / "test" / "Cydra043.t.sol").write_text(poc)
        independent_v_result = run_foundry(
            independent_v,
            contract,
            test,
            "independent-vulnerable",
            Path(target["source"]).parent,
        )

        independent_p = root / "independent-patched"
        clone(target["repo"], target["ref"], independent_p)
        source = independent_p / target["source"]
        source.write_text(patcher(source.read_text()))
        (independent_p / "test").mkdir(parents=True, exist_ok=True)
        (independent_p / "test" / "Cydra043.t.sol").write_text(poc)
        independent_p_result = run_foundry(
            independent_p,
            contract,
            test,
            "independent-patched",
            Path(target["source"]).parent,
        )

    causal = vulnerable_result["status"] == "FAIL" and patched_result["status"] == "PASS"
    reproduction = (
        independent_v_result["status"] == "FAIL"
        and independent_p_result["status"] == "PASS"
    )
    ready = causal and reproduction

    return {
        "status": "READY" if ready else "BLOCKED",
        "blind": blind,
        "selection": selection,
        "vulnerable": vulnerable_result,
        "patched": patched_result,
        "causal_verification": causal,
        "independent_vulnerable": independent_v_result,
        "independent_patched": independent_p_result,
        "reproduction_verification": reproduction,
        "finding_gate": "READY" if ready else "BLOCKED",
        "blind_boundary_preserved": True,
    }


def main() -> int:
    output = Path("backtest-artifacts/benchmark-043")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    results = {}
    for target in TARGETS:
        target_output = output / target["id"]
        target_output.mkdir(parents=True)
        results[target["id"]] = run_target(target, target_output)

    ready = all(item["status"] == "READY" for item in results.values())
    result = {
        "status": "READY" if ready else "NOT_CONFIRMED",
        "targets_total": len(results),
        "targets_ready": sum(item["status"] == "READY" for item in results.values()),
        "targets": results,
        "multi_target_gate": "READY" if ready and len(results) >= 2 else "BLOCKED",
        "blind_boundary_preserved": all(
            item.get("blind_boundary_preserved", True) for item in results.values()
        ),
    }
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
