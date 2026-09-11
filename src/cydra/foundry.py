from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess

from .models import Evidence, Hypothesis


@dataclass(frozen=True)
class ExecutionResult:
    experiment_id: str
    target: str
    command: tuple[str, ...]
    exit_code: int
    passed: bool
    stdout: str
    stderr: str


@dataclass(frozen=True)
class ExperimentOutcome:
    hypothesis: Hypothesis
    vulnerable: ExecutionResult
    patched: ExecutionResult
    evidence: tuple[Evidence, ...]


def _write_test(source: str, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def generate_access_control_test(hypothesis: Hypothesis, target_import: str, target_type: str, output_path: str | Path) -> Path:
    if hypothesis.invariant_id != "INV-AUTH-001":
        raise ValueError(f"Unsupported invariant for Foundry generation: {hypothesis.invariant_id}")
    return _write_test(f'''// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;
// Hypothesis: {hypothesis.hypothesis_id}
import {{Test}} from "forge-std/Test.sol";
import {{ {target_type} }} from "{target_import}";
contract CydraAuthInvariantTest is Test {{
    {target_type} internal target;
    address internal attacker = address(0xBEEF);
    address internal account = address(0xCAFE);
    function setUp() public {{ target = new {target_type}(); }}
    function testUnauthorizedCallerCannotMutatePrivilegedState() public {{
        assertFalse(target.whiteList(account));
        vm.expectRevert(); vm.prank(attacker); target.setWhitelist(account, true);
        assertFalse(target.whiteList(account));
    }}
}}
''', output_path)


def generate_initialization_test(hypothesis: Hypothesis, target_import: str, target_type: str, output_path: str | Path) -> Path:
    if hypothesis.invariant_id != "INV-INIT-001":
        raise ValueError(f"Unsupported invariant for Foundry generation: {hypothesis.invariant_id}")
    return _write_test(f'''// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;
// Hypothesis: {hypothesis.hypothesis_id}
import {{Test}} from "forge-std/Test.sol";
import {{ {target_type} }} from "{target_import}";
contract CydraInitializationInvariantTest is Test {{
    {target_type} internal target;
    address internal attacker = address(0xBEEF);
    function setUp() public {{ target = new {target_type}(); }}
    function testArbitraryCallerCannotClaimInitializationState() public {{
        (bool ok,) = address(target).call(abi.encodeWithSelector(target.initialize.selector, attacker));
        assertTrue(!ok || target.guardian() != attacker, "attacker claimed privileged initialization state");
    }}
}}
''', output_path)


def run_foundry_test(project_dir: str | Path, test_path: str | Path, experiment_id: str, target: str) -> ExecutionResult:
    project = Path(project_dir)
    relative_test = Path(test_path)
    if relative_test.is_absolute(): relative_test = relative_test.relative_to(project)
    command = ("forge", "test", "--match-path", str(relative_test), "-vv")
    completed = subprocess.run(command, cwd=project, text=True, capture_output=True, check=False)
    return ExecutionResult(experiment_id, target, command, completed.returncode, completed.returncode == 0, completed.stdout, completed.stderr)


def classify_access_control_outcome(hypothesis: Hypothesis, vulnerable: ExecutionResult, patched: ExecutionResult) -> ExperimentOutcome:
    return _classify(hypothesis, vulnerable, patched)


def classify_initialization_outcome(hypothesis: Hypothesis, vulnerable: ExecutionResult, patched: ExecutionResult) -> ExperimentOutcome:
    return _classify(hypothesis, vulnerable, patched)


def _classify(hypothesis: Hypothesis, vulnerable: ExecutionResult, patched: ExecutionResult) -> ExperimentOutcome:
    if not vulnerable.passed and patched.passed: status = "confirmed"
    elif vulnerable.passed and not patched.passed: status = "rejected"
    else: status = "proposed"
    updated = Hypothesis(hypothesis.hypothesis_id, hypothesis.claim, hypothesis.invariant_id, hypothesis.target_function, hypothesis.attacker_capability, hypothesis.expected_impact, status, hypothesis.evidence_ids + (f"E-EXEC-{hypothesis.hypothesis_id}-VULNERABLE", f"E-EXEC-{hypothesis.hypothesis_id}-PATCHED"))
    evidence = (
        Evidence(f"E-EXEC-{hypothesis.hypothesis_id}-VULNERABLE", "execution", f"Foundry security test against vulnerable target exited {vulnerable.exit_code}; passed={vulnerable.passed}.", " ".join(vulnerable.command), vulnerable.target),
        Evidence(f"E-EXEC-{hypothesis.hypothesis_id}-PATCHED", "execution", f"Foundry security test against patched target exited {patched.exit_code}; passed={patched.passed}.", " ".join(patched.command), patched.target),
    )
    return ExperimentOutcome(updated, vulnerable, patched, evidence)
