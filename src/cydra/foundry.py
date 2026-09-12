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
    project = Path(project_dir)
    config_path = project / "foundry.toml"
    test_dir = "test"
    if config_path.exists():
        with config_path.open("rb") as handle:
            config = tomllib.load(handle)
        test_dir = config.get("profile", {}).get("default", {}).get("test", test_dir)
    return project / test_dir


def test_path_for(project_dir: str | Path, filename: str) -> Path:
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


def _constructor_argument(parameter: ParameterModel, runtime_arguments: dict[str, str] | None = None) -> str:
    runtime_arguments = runtime_arguments or {}
    if parameter.name in runtime_arguments:
        return runtime_arguments[parameter.name]
    parameter_type = parameter.type.strip()
    if parameter_type.startswith("address"):
        return "payable(address(0))" if parameter_type == "address payable" else "address(0)"
    if parameter_type.startswith(("uint", "int")):
        return "0"
    if parameter_type == "bool":
        return "false"
    if parameter_type == "string":
        return '\"\"'
    if parameter_type == "bytes":
        return "bytes(\\\"\\\")"
    if parameter_type.startswith("bytes"):
        return "0"
    if parameter_type.endswith("[]"):
        return f"new {parameter_type[:-2]}[](0)"
    return "address(0)"


def _initializer_argument(parameter: ParameterModel, target_type: str, index: int, runtime_arguments: dict[str, str] | None = None) -> tuple[str, str | None]:
    runtime_arguments = runtime_arguments or {}
    if parameter.name in runtime_arguments:
        return runtime_arguments[parameter.name], None
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
        return '\"\"', None
    if parameter_type == "bytes":
        return "bytes(\\\"\\\")", None
    if parameter_type.startswith("bytes"):
        return "0", None
    variable = f"parameter{index}"
    declaration = f"{target_type}.{parameter_type} memory {variable};"
    return variable, declaration


def _layout_aware_import_path(target_import: str, output_path: str | Path) -> str:
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


def _source_text(contract_model: ContractModel) -> str:
    try:
        return Path(contract_model.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""


def _initializer_runtime_requirements(contract_model: ContractModel, function_name: str) -> tuple[set[str], bool]:
    source = _source_text(contract_model)
    if not source:
        return set(), False
    function_match = re.search(rf"\bfunction\s+{re.escape(function_name)}\s*\([^)]*\)[^{{;]*\{{", source, re.MULTILINE)
    if not function_match:
        return set(), False
    body = source[function_match.end():]
    depth = 1
    end = len(body)
    for index, char in enumerate(body):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                end = index
                break
    body = body[:end]
    token_parameters = {
        parameter
        for receiver, parameter, method in re.findall(r"\b([A-Za-z_]\w*)\s*\(\s*(\w+)\s*\)\.(\w+)\s*\(", body)
        if receiver == "ERC20" and method == "symbol"
    }
    factory_context = bool(re.search(r"\b\w+\s*=\s*_msgSender\s*\(\s*\)\s*;", body)) and bool(
        re.search(r"\bIPoolFactory\s*\(\s*\w+\s*\)\s*\.\s*voter\s*\(", body)
    )
    return token_parameters, factory_context


def _solidity_default_value(return_declaration: str) -> str:
    declaration = return_declaration.strip()
    if not declaration:
        raise ValueError("Cannot generate a default value for an empty return declaration")
    tokens = declaration.replace("\t", " ").split()
    parameter_type = tokens[0]
    if parameter_type.startswith("address"):
        return "address(0)"
    if parameter_type.startswith(("uint", "int")) or parameter_type.startswith("bytes") and parameter_type != "bytes":
        return "0"
    if parameter_type == "bool":
        return "false"
    if parameter_type == "string":
        return '\"\"'
    if parameter_type == "bytes":
        return "bytes(\"\")"
    if parameter_type.endswith("[]"):
        return f"new {parameter_type[:-2]}[](0)"
    if parameter_type.startswith("tuple"):
        raise ValueError(f"Unsupported tuple return in generated stub: {return_declaration}")
    return "0"


def _semantic_override(interface_name: str, method_name: str) -> str | None:
    if interface_name == "IERC20":
        return {
            "symbol": '\"CYDRA\"',
            "decimals": "18",
            "approve": "true",
            "transfer": "true",
            "transferFrom": "true",
            "totalSupply": "0",
            "balanceOf": "0",
            "allowance": "0",
        }.get(method_name)
    return None


def _stub_method_source(interface_name: str, method, derived_returns: dict[str, str]) -> str:
    parameters = ", ".join(method.parameters)
    returns = ", ".join(method.returns)
    signature = f"function {method.name}({parameters}) external view"
    if returns:
        signature += f" returns ({returns})"
    signature += " {"

    if method.name in derived_returns:
        value = derived_returns[method.name]
        if len(method.returns) != 1:
            raise ValueError(f"Derived interface method {interface_name}.{method.name} must have exactly one return value")
        return f"    {signature} return {value}; }}"

    if not method.returns:
        return f"    {signature} }}"

    override = _semantic_override(interface_name, method.name)
    values = [override if override is not None else _solidity_default_value(item) for item in method.returns]
    expression = values[0] if len(values) == 1 else f"({', '.join(values)})"
    return f"    {signature} return {expression}; }}"


def _runtime_stub_source(
    resolved_interface_casts: tuple[tuple[str, object], ...],
    derived_interface_casts: tuple[tuple[str, str, object], ...],
) -> tuple[str, dict[str, str]]:
    resolved: dict[str, object] = {interface.name: interface for _, interface in resolved_interface_casts}
    derived_targets: dict[str, object] = {interface.name: interface for _, _, interface in derived_interface_casts}
    interfaces: dict[str, object] = dict(resolved)
    interfaces.update(derived_targets)

    derived_by_source: dict[str, list[tuple[str, object]]] = {}
    for source_interface, source_method, target_interface in derived_interface_casts:
        derived_by_source.setdefault(source_interface, []).append((source_method, target_interface))
        if source_interface not in resolved:
            raise ValueError(f"Derived source interface {source_interface} is not present in resolved_interface_casts")

    variables: dict[str, str] = {}
    for interface_name in sorted(interfaces):
        variables[interface_name] = f"{interface_name[1:]}Stub"

    def deployment_order() -> tuple[str, ...]:
        visiting: set[str] = set()
        visited: set[str] = set()
        order: list[str] = []

        def visit(interface_name: str) -> None:
            if interface_name in visited:
                return
            if interface_name in visiting:
                raise ValueError(f"Cyclic derived interface dependency: {interface_name}")
            visiting.add(interface_name)
            for _, target in derived_by_source.get(interface_name, ()):
                visit(target.name)
            visiting.remove(interface_name)
            visited.add(interface_name)
            order.append(interface_name)

        for interface_name in sorted(interfaces):
            visit(interface_name)
        return tuple(order)

    declarations: list[str] = []
    for interface_name in sorted(interfaces):
        interface = interfaces[interface_name]
        relations = derived_by_source.get(interface_name, ())
        fields = "".join(f"    address internal _cydraDerived_{method};\n" for method, _ in relations)
        constructor = ""
        if relations:
            parameters = ", ".join(f"address {method}Target" for method, _ in relations)
            assignments = " ".join(f"_cydraDerived_{method} = {method}Target;" for method, _ in relations)
            constructor = f"    constructor({parameters}) {{ {assignments} }}\n"
        derived_returns = {method: f"_cydraDerived_{method}" for method, _ in relations}
        methods = "\n".join(_stub_method_source(interface_name, method, derived_returns) for method in interface.methods)
        declarations.append(
            f'''contract Cydra{interface_name}Stub {{
{fields}{constructor}{methods}
    fallback() external payable {{}}
    receive() external payable {{}}
}}'''
        )

    return "\n\n".join(declarations), variables


def _model_initialization_source(
    hypothesis: Hypothesis,
    target_import: str,
    target_type: str,
    contract_model: ContractModel,
    output_path: str | Path | None = None,
) -> str:
    if output_path is not None:
        target_import = _layout_aware_import_path(target_import, output_path)
        print("PROBE5G: emitted target import =", target_import)
    constructor = contract_model.constructor
    function = next((candidate for candidate in contract_model.functions if candidate.name == hypothesis.target_function), None)
    if function is None:
        raise ValueError(f"Model has no target function: {hypothesis.target_function}")

    resolved_interface_casts = constructor.resolved_interface_casts if constructor else ()
    derived_interface_casts = constructor.derived_interface_casts if constructor else ()
    token_parameters, factory_context = _initializer_runtime_requirements(contract_model, function.name)
    stub_source, stub_variables = _runtime_stub_source(resolved_interface_casts, derived_interface_casts)

    constructor_runtime_arguments = {
        parameter: f"address({stub_variables[interface]})"
        for parameter, interface in (constructor.interface_casts if constructor else ())
    }
    constructor_arguments = ""
    if constructor is not None and constructor.parameters:
        constructor_arguments = ", ".join(_constructor_argument(p, constructor_runtime_arguments) for p in constructor.parameters)

    initializer_runtime_arguments = {parameter: "address(tokenStub)" for parameter in token_parameters}
    arguments: list[str] = []
    declarations: list[str] = []
    for index, parameter in enumerate(function.parameters):
        argument, declaration = _initializer_argument(parameter, target_type, index, initializer_runtime_arguments)
        arguments.append(argument)
        if declaration:
            declarations.append(declaration)
    initialize_call = f"target.{function.name}({', '.join(arguments)});"
    declarations_text = "\n        ".join(declarations)
    if declarations_text:
        declarations_text += "\n        "
    pragma = contract_model.pragma or "^0.8.20"

    factory_method = "\n    function voter() external view returns (address) { return address(this); }" if factory_context else ""
    derived_by_source: dict[str, list[tuple[str, object]]] = {}
    for source_interface, source_method, target_interface in derived_interface_casts:
        derived_by_source.setdefault(source_interface, []).append((source_method, target_interface))

    deployment_names: list[str] = []
    deployed: set[str] = set()
    visiting: set[str] = set()
    resolved_names = {interface.name for _, interface in resolved_interface_casts}
    derived_targets = {interface.name for _, _, interface in derived_interface_casts}
    all_interface_names = sorted(resolved_names | derived_targets)

    def schedule(interface_name: str) -> None:
        if interface_name in deployed:
            return
        if interface_name in visiting:
            raise ValueError(f"Cyclic derived interface dependency: {interface_name}")
        visiting.add(interface_name)
        for _, target_interface in derived_by_source.get(interface_name, ()):
            schedule(target_interface.name)
        visiting.remove(interface_name)
        deployed.add(interface_name)
        deployment_names.append(interface_name)

    for interface_name in all_interface_names:
        schedule(interface_name)

    stub_deployments = "\n        ".join(
        (
            f"{stub_variables[interface_name]} = new Cydra{interface_name}Stub();"
            if not derived_by_source.get(interface_name)
            else f"{stub_variables[interface_name]} = new Cydra{interface_name}Stub("
            + ", ".join(f"address({stub_variables[target_interface.name]})" for _, target_interface in derived_by_source[interface_name])
            + ");"
        )
        for interface_name in deployment_names
    )
    token_deployment = "tokenStub = new CydraERC20Stub();" if token_parameters else ""
    token_declaration = "    CydraERC20Stub internal tokenStub;\n" if token_parameters else ""
    interface_declarations = "".join(f"    Cydra{interface_name}Stub internal {stub_variables[interface_name]};\n" for interface_name in all_interface_names)

    return f'''// SPDX-License-Identifier: UNLICENSED
pragma solidity {pragma};
// Hypothesis: {hypothesis.hypothesis_id}
// Interface-aware generation only: constructor and initializer parameter shapes
// come from ContractModel/FunctionModel. Runtime dependencies are real local stubs.
import {{Test}} from "forge-std/Test.sol";
import {{ {target_type} }} from "{target_import}";
{stub_source}
contract CydraInitializationInvariantTest is Test {{
    {target_type} internal target;
{interface_declarations}{token_declaration}{factory_method}
    function setUp() public {{
        {stub_deployments}
        {token_deployment}
        target = new {target_type}({constructor_arguments});
    }}
    function testInitializationInterfaceIsCallable() public {{
        {declarations_text}{initialize_call}
    }}
}}
'''


def generate_initialization_test(hypothesis: Hypothesis, target_import: str, target_type: str, output_path: str | Path, contract_model: ContractModel | None = None) -> Path:
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
    return _write_test(_model_initialization_source(hypothesis, target_import, target_type, contract_model, output_path), output_path)


def generate_arithmetic_foundry_test(experiment: Experiment, target: str, patched: str) -> str:
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
