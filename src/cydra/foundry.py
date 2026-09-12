from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import re
import subprocess
import tomllib
from typing import Literal

from .models import ContractModel, Evidence, Experiment, FunctionModel, Hypothesis, ParameterModel


ExecutionStatus = Literal["PASS", "FAIL", "UNMEASURABLE"]


@dataclass(frozen=True)
class ExecutionResult:
    experiment_id: str
    target: str
    command: tuple[str, ...]
    exit_code: int
    executed: bool
    tests_run: int
    tests_failed: int
    status: ExecutionStatus
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


def configured_test_dir(project_dir: str | Path) -> Path:
    """Return the Foundry test directory declared by the project's config."""
    project = Path(project_dir)
    config_path = project / "foundry.toml"
    test_dir = "test"
    if config_path.exists():
        with config_path.open("rb") as handle:
            config = tomllib.load(handle)
        test_dir = config.get("profile", {}).get("default", {}).get("test", test_dir)
    return project / test_dir


def test_path_for(project_dir: str | Path, filename: str) -> Path:
    """Build a generated-test path from Foundry's configured test directory."""
    return configured_test_dir(project_dir) / filename


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


def _constructor_argument(parameter: ParameterModel) -> str:
    parameter_type = parameter.type.strip()
    if parameter_type.startswith("address"):
        return "payable(address(0))" if parameter_type == "address payable" else "address(0)"
    if parameter_type.startswith(("uint", "int")):
        return "0"
    if parameter_type == "bool":
        return "false"
    if parameter_type == "string":
        return '""'
    if parameter_type == "bytes":
        return "bytes(\"\")"
    if parameter_type.startswith("bytes"):
        return "0"
    if parameter_type.endswith("[]"):
        return f"new {parameter_type[:-2]}[](0)"
    return "address(0)"


def _initializer_argument(parameter: ParameterModel, target_type: str, index: int) -> tuple[str, str | None]:
    parameter_type = parameter.type.strip()
    if parameter_type.endswith("[]"):
        return f"new {parameter_type[:-2]}[](0)", None
    if parameter_type.startswith("address"):
        return ("payable(address(0))" if parameter_type == "address payable" else "address(0)"), None
    if parameter_type.startswith(("uint", "int")):
        return "0", None
    if parameter_type == "bool":
        return "false", None
    if parameter_type == "string":
        return '""', None
    if parameter_type == "bytes":
        return "bytes(\"\")", None
    if parameter_type.startswith("bytes"):
        return "0", None
    variable = f"parameter{index}"
    declaration = f"{target_type}.{parameter_type} memory {variable};"
    return variable, declaration


def _layout_aware_import_path(target_import: str, output_path: str | Path) -> str:
    """Resolve a project-relative target and rebase it on the generated test directory."""
    output = Path(output_path)
    for ancestor in (output.parent, *output.parents):
        if (ancestor / "foundry.toml").exists():
            raw = Path(target_import)
            if raw.is_absolute():
                candidate = raw
            else:
                parts = list(raw.parts)
                while parts and parts[0] == "..":
                    parts.pop(0)
                candidate = ancestor.joinpath(*parts)
            if candidate.exists():
                return Path(os.path.relpath(candidate, output.parent)).as_posix()
            break
    return target_import


def _model_initialization_source(
    hypothesis: Hypothesis,
    target_import: str,
    target_type: str,
    contract_model: ContractModel,
    output_path: str | Path | None = None,
) -> str:
    print("PROBE2: contract_model id =", id(contract_model))
    print("PROBE2: function names =", [f.name for f in contract_model.functions])
    print("PROBE2: hypothesis id =", id(hypothesis))
    print("PROBE2: hypothesis repr =", repr(hypothesis))
    print("PROBE2: target_function repr =", repr(hypothesis.target_function))
    print("PROBE2: target_function bytes =", hypothesis.target_function.encode())
    print("PROBE2: any name == target_function =", any(f.name == hypothesis.target_function for f in contract_model.functions))
    print("PROBE2: any name == 'initialize' =", any(f.name == "initialize" for f in contract_model.functions))
    if output_path is not None:
        target_import = _layout_aware_import_path(target_import, output_path)
        print("PROBE5G: emitted target import =", target_import)
    constructor = contract_model.constructor
    constructor_arguments = ""
    if constructor is not None and constructor.parameters:
        constructor_arguments = ", ".join(_constructor_argument(p) for p in constructor.parameters)
    function = next((candidate for candidate in contract_model.functions if candidate.name == hypothesis.target_function), None)
    if function is None:
        raise ValueError(f"Model has no target function: {hypothesis.target_function}")
    arguments: list[str] = []
    declarations: list[str] = []
    for index, parameter in enumerate(function.parameters):
        argument, declaration = _initializer_argument(parameter, target_type, index)
        arguments.append(argument)
        if declaration:
            declarations.append(declaration)
    initialize_call = f"target.{function.name}({', '.join(arguments)});"
    declarations_text = "\n        ".join(declarations)
    if declarations_text:
        declarations_text += "\n        "
    return f'''// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;
// Hypothesis: {hypothesis.hypothesis_id}
// Interface-aware generation only: constructor and initializer parameter shapes
// come from ContractModel/FunctionModel. Postcondition semantics are deferred.
import {{Test}} from "forge-std/Test.sol";
import {{ {target_type} }} from "{target_import}";
contract CydraInitializationInvariantTest is Test {{
    {target_type} internal target;
    function setUp() public {{ target = new {target_type}({constructor_arguments}); }}
    function testInitializationInterfaceIsCallable() public {{
        {declarations_text}{initialize_call}
    }}
}}
'''


def generate_initialization_test(
    hypothesis: Hypothesis,
    target_import: str,
    target_type: str,
    output_path: str | Path,
    contract_model: ContractModel | None = None,
) -> Path:
    if hypothesis.invariant_id != "INV-INIT-001":
        raise ValueError(f"Unsupported invariant for Foundry generation: {hypothesis.invariant_id}")
    if contract_model is None:
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
    return _write_test(
        _model_initialization_source(hypothesis, target_import, target_type, contract_model, output_path),
        output_path,
    )


def generate_arithmetic_foundry_test(experiment: Experiment, target: str, patched: str) -> str:
    """Generate the arithmetic differential Foundry test without executing it."""
    if not experiment.experiment_id.startswith("X-H-ARITH-"):
        raise ValueError(f"Unsupported experiment for arithmetic Foundry generation: {experiment.experiment_id}")
    def parse_target(spec: str) -> tuple[str, str]:
        try:
            import_path, contract_type = spec.rsplit(":", 1)
        except ValueError as exc:
            raise ValueError("Arithmetic target must be '<import-path>:<contract-type>'") from exc
        if not import_path or not contract_type:
            raise ValueError("Arithmetic target must include import path and contract type")
        return import_path, contract_type
    target_import, target_type = parse_target(target)
    patched_import, patched_type = parse_target(patched)
    return f'''// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;
// Hypothesis: {experiment.hypothesis_id}
import {{Test}} from "forge-std/Test.sol";
import {{ {target_type} as Vulnerable }} from "{target_import}";
import {{ {patched_type} as Patched }} from "{patched_import}";
contract CydraArithmeticInvariantTest is Test {{
    function testArithmeticBoundaryPreservesExactFloor() public {{
        Vulnerable vulnerable = new Vulnerable();
        Patched patchedTarget = new Patched();
        uint256 assets = 1;
        uint256 exactFloor = (assets * vulnerable.SCALE()) / 997;
        uint256 vulnerableObserved = vulnerable.quoteMint(assets);
        uint256 patchedObserved = patchedTarget.quoteMint(assets);
        assertGt(vulnerableObserved, exactFloor);
        assertEq(patchedObserved, exactFloor);
    }}
}}
'''


def _parse_execution(stdout: str, stderr: str, exit_code: int) -> tuple[bool, int, int, ExecutionStatus]:
    output = f"{stdout}\n{stderr}"
    if "No tests found" in output:
        return False, 0, 0, "UNMEASURABLE"
    ran_matches = re.findall(r"Ran\s+(\d+)\s+tests?\s+for\s+", output)
    tests_run = int(ran_matches[-1]) if ran_matches else 0
    failed_matches = re.findall(r"Suite result:.*?(\d+)\s+passed;\s+(\d+)\s+failed", output)
    tests_failed = int(failed_matches[-1][1]) if failed_matches else (tests_run if exit_code != 0 and tests_run else 0)
    if tests_run == 0:
        return False, 0, tests_failed, "UNMEASURABLE"
    if exit_code == 0 and tests_failed == 0:
        return True, tests_run, 0, "PASS"
    return True, tests_run, tests_failed, "FAIL"


def run_foundry_test(project_dir: str | Path, test_path: str | Path, experiment_id: str, target: str) -> ExecutionResult:
    project = Path(project_dir)
    relative_test = Path(test_path)
    if relative_test.is_absolute():
        relative_test = relative_test.relative_to(project)
    command = ("forge", "test", "--match-path", str(relative_test), "-vv")
    completed = subprocess.run(command, cwd=project, text=True, capture_output=True, check=False)
    executed, tests_run, tests_failed, status = _parse_execution(completed.stdout, completed.stderr, completed.returncode)
    return ExecutionResult(experiment_id, target, command, completed.returncode, executed, tests_run, tests_failed, status, completed.stdout, completed.stderr)


def require_executed(result: ExecutionResult) -> ExecutionResult:
    """Hard causal gate: zero-test execution cannot reach classification."""
    if not result.executed or result.tests_run == 0 or result.status == "UNMEASURABLE":
        raise RuntimeError(f"Foundry experiment {result.experiment_id} is UNMEASURABLE: executed={result.executed}, tests_run={result.tests_run}, exit_code={result.exit_code}")
    return result


def classify_access_control_outcome(hypothesis: Hypothesis, vulnerable: ExecutionResult, patched: ExecutionResult) -> ExperimentOutcome:
    return _classify(hypothesis, vulnerable, patched)


def classify_initialization_outcome(hypothesis: Hypothesis, vulnerable: ExecutionResult, patched: ExecutionResult) -> ExperimentOutcome:
    return _classify(hypothesis, vulnerable, patched)


def _classify(hypothesis: Hypothesis, vulnerable: ExecutionResult, patched: ExecutionResult) -> ExperimentOutcome:
    if vulnerable.status == "UNMEASURABLE" or patched.status == "UNMEASURABLE":
        status = "proposed"
    elif vulnerable.status == "FAIL" and patched.status == "PASS":
        status = "confirmed"
    elif vulnerable.status == "PASS" and patched.status == "FAIL":
        status = "rejected"
    else:
        status = "proposed"
    updated = Hypothesis(hypothesis.hypothesis_id, hypothesis.claim, hypothesis.invariant_id, hypothesis.target_function, hypothesis.attacker_capability, hypothesis.expected_impact, status, hypothesis.evidence_ids + (f"E-EXEC-{hypothesis.hypothesis_id}-VULNERABLE", f"E-EXEC-{hypothesis.hypothesis_id}-PATCHED"))
    evidence = (Evidence(f"E-EXEC-{hypothesis.hypothesis_id}-VULNERABLE", "execution", f"Foundry security test against vulnerable target: status={vulnerable.status}, executed={vulnerable.executed}, tests_run={vulnerable.tests_run}, tests_failed={vulnerable.tests_failed}, exit={vulnerable.exit_code}.", " ".join(vulnerable.command), vulnerable.target), Evidence(f"E-EXEC-{hypothesis.hypothesis_id}-PATCHED", "execution", f"Foundry security test against patched target: status={patched.status}, executed={patched.executed}, tests_run={patched.tests_run}, tests_failed={patched.tests_failed}, exit={patched.exit_code}.", " ".join(patched.command), patched.target))
    return ExperimentOutcome(updated, vulnerable, patched, evidence)
