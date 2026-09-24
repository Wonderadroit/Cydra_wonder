from __future__ import annotations

from pathlib import Path
from .interface_resolver import resolve_interface, resolve_named_type_source
from .execution_readiness import _address_role, caller_role, constructible_state_setup_plan, inspect_execution_readiness
from .experiment_inputs import conservative_defaults

from .models import ContractModel, Experiment, Hypothesis
from .solidity_model import parse_solidity
from .planned_call import render_function_call


def generate_authorization_test_from_experiment(
    hypothesis: Hypothesis,
    experiment: Experiment,
    target_import: str,
    target_type: str,
    output_path: str | Path,
    contract_model: ContractModel,
    *,
    semantic_evidence=(),
    constraints=(),
) -> Path:
    """Generate an authorization experiment from the canonical Experiment plan.

    The Experiment owns the ordered ABI vector. This renderer deliberately does not
    reconstruct arguments from the hypothesis or benchmark name, so compiler-derived
    constraints can reach the actual Foundry call without class-specific argument
    heuristics.
    """
    if hypothesis.invariant_id != "INV-AUTH-001":
        raise ValueError(f"Unsupported invariant for Foundry generation: {hypothesis.invariant_id}")
    if experiment.hypothesis_id != hypothesis.hypothesis_id:
        raise ValueError(
            f"experiment/hypothesis mismatch: {experiment.hypothesis_id} != {hypothesis.hypothesis_id}"
        )

    function = next(
        (candidate for candidate in contract_model.functions if candidate.name == hypothesis.target_function),
        None,
    )
    if function is None:
        raise ValueError(f"Model has no target function: {hypothesis.target_function}")

    call = render_function_call(experiment, function)
    signature_types = ", ".join(parameter.type.split()[0] for parameter in function.parameters)
    arguments = call.removeprefix(f"target.{function.name}(").removesuffix(");")
    pragma = contract_model.pragma or "^0.8.20"
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    project_root = next(
        (ancestor for ancestor in (path.parent, *path.parents) if (ancestor / "foundry.toml").exists()),
        None,
    )
    role_addresses = {"owner": "address(0x1001)", "admin": "address(0x1002)", "guardian": "address(0x1003)", "risk_manager": "address(0x1004)", "liquidator": "address(0x1005)", "factory": "address(0x1006)"}
    constructor_arguments: list[str] = []
    constructor_imports: list[str] = []
    inherited_interfaces = {item.name: item for item in contract_model.inherited_resolved_interfaces}
    direct_interfaces: dict[str, object] = {}
    named_type_sources: dict[str, str] = {}
    erc20_stub_needed = False
    if project_root is not None and contract_model.constructor is not None:
        for parameter in contract_model.constructor.parameters:
            base = parameter.type.strip().split()[0].rstrip("[]")
            if base in inherited_interfaces:
                direct_interfaces[base] = inherited_interfaces[base]
            elif "." not in base and base not in {"address", "bool", "string", "bytes"} and not base.startswith(("uint", "int", "bytes")):
                try:
                    direct_interfaces[base] = resolve_interface(project_root, contract_model.source, base)
                except (FileNotFoundError, ValueError, OSError, UnicodeError):
                    try:
                        source_path, _ = resolve_named_type_source(project_root, contract_model.source, base)
                        named_type_sources[base] = source_path
                    except (FileNotFoundError, ValueError, OSError, UnicodeError):
                        pass

    for parameter in (contract_model.constructor.parameters if contract_model.constructor else ()):
        parameter_type = parameter.type.strip()
        base = parameter_type.split()[0].rstrip("[]")
        if parameter_type.endswith("[]"):
            raise ValueError(f"unsupported authorization constructor array type: {parameter.type}")
        if base == "address":
            role = _address_role(parameter.name)
            constructor_arguments.append(role_addresses.get(role, "address(0)"))
        elif parameter_type == "address payable":
            constructor_arguments.append("payable(address(0))")
        elif base == "bool":
            constructor_arguments.append("false")
        elif base.startswith(("uint", "int")):
            constructor_arguments.append("0")
        elif base == "string":
            constructor_arguments.append('""')
        elif base == "bytes":
            constructor_arguments.append('bytes("")')
        elif base.startswith("bytes") and base[5:].isdigit():
            constructor_arguments.append("0")
        elif base in direct_interfaces:
            constructor_arguments.append(f"{base}(address(0))")
            resolved = direct_interfaces[base]
            relative = Path(__import__("os").path.relpath(project_root / resolved.source_path, path.parent)).as_posix()
            constructor_imports.append(f'import {{ {base} }} from "{relative}";')
        elif base in named_type_sources:
            if base == "ERC20":
                erc20_stub_needed = True
                constructor_arguments.append("ERC20(address(constructorAsset))")
            else:
                constructor_arguments.append(f"{base}(address(0))")
            resolved_path = Path(project_root / named_type_sources[base])
            relative = Path(__import__("os").path.relpath(resolved_path, path.parent)).as_posix()
            constructor_imports.append(f'import {{ {base} }} from "{relative}";')
        else:
            raise ValueError(f"unsupported authorization constructor type: {parameter.type}")

    constructor_args_text = ", ".join(constructor_arguments)
    constructor_call = f"new {target_type}({constructor_args_text})" if constructor_arguments else f"new {target_type}()"
    constructor_import_text = "\n".join(dict.fromkeys(constructor_imports))

    stub_declaration = (
        'contract CydraERC20ConstructorStub is ERC20 { constructor() ERC20("CYDRA", "CYDRA", 18) {} }\n'
        if erc20_stub_needed else ""
    )
    asset_declaration = "    ERC20 internal constructorAsset;\n" if erc20_stub_needed else ""
    asset_setup = "        constructorAsset = new CydraERC20ConstructorStub();\n" if erc20_stub_needed else ""
    functions_by_name = {item.name: item for item in (*contract_model.inherited_functions, *contract_model.functions)}
    readiness_contract = contract_model
    try:
        parsed_contract = parse_solidity(Path(contract_model.source))[0]
        for parsed_function in parsed_contract.functions:
            functions_by_name.setdefault(parsed_function.name, parsed_function)
        if len(functions_by_name) > len(contract_model.functions) + len(contract_model.inherited_functions):
            readiness_contract = ContractModel(
                name=contract_model.name,
                source=contract_model.source,
                functions=tuple(functions_by_name.values()),
                constructor=contract_model.constructor,
                pragma=contract_model.pragma,
                state_variables=contract_model.state_variables,
                inherits=contract_model.inherits,
                declared_types=contract_model.declared_types,
                inherited_resolved_interfaces=contract_model.inherited_resolved_interfaces,
                inherited_functions=contract_model.inherited_functions,
            )
    except (OSError, ValueError, IndexError):
        pass
    readiness = inspect_execution_readiness(readiness_contract, function, constraints, semantic_evidence)
    caller_bindings = {
        "owner": "owner",
        "admin": "admin",
        "guardian": "guardian",
        "risk_manager": "riskManager",
        "liquidator": "liquidator",
        "factory": "factory",
    }
    setup_lines: list[str] = []
    caller_setup_subjects = {
        requirement.subject
        for requirement in readiness.execution_requirements
        if requirement.kind == "caller_state_setup_candidate"
    }
    if caller_setup_subjects:
        setup_plan = constructible_state_setup_plan(
            readiness_contract,
            function,
            constraints,
            semantic_evidence,
        )
        planned_functions = {action.function for action in setup_plan}
        unresolved = sorted(caller_setup_subjects - planned_functions)
        if unresolved:
            raise ValueError(
                "unresolved caller-state setup prerequisite(s): " + ", ".join(unresolved)
            )
    else:
        setup_plan = constructible_state_setup_plan(
            readiness_contract,
            function,
            constraints,
            semantic_evidence,
        )
    for action in setup_plan:
        writer = functions_by_name.get(action.function)
        if writer is None:
            raise ValueError(f"execution-readiness setup function is not modeled: {action.function}")
        defaults = conservative_defaults(writer.parameters)
        if defaults is None or any(not defaults.get(parameter.name, "") for parameter in writer.parameters):
            raise ValueError(
                f"execution-readiness setup function lacks constructible default inputs: {action.function}"
            )
        arguments = ", ".join(defaults.get(parameter.name, "") for parameter in writer.parameters)
        role = caller_bindings.get(action.caller_role, "attacker")
        setup_lines.append(
            f"        vm.prank({role});\\n"
            f"        try target.{writer.name}({arguments}) {{}} catch {{ setupOk = false; }}"
        )

    setup_guard = (
        "        bool setupOk = true;\n"
        + "\n".join(dict.fromkeys(setup_lines))
        + "\n        assertTrue(setupOk, \"execution-readiness setup failed\");\n"
    ) if setup_lines else ""
    source = f'''// SPDX-License-Identifier: UNLICENSED
pragma solidity {pragma};
// Hypothesis: {hypothesis.hypothesis_id}
// Experiment: {experiment.experiment_id}
// Planned inputs are authoritative for this concrete target call.
import {{Test}} from "forge-std/Test.sol";
import {{ {target_type} }} from "{target_import}";
{constructor_import_text}

{stub_declaration}contract CydraAuthInvariantTest is Test {{
    {target_type} internal target;
    address internal attacker = address(0xBEEF);
    address internal owner = address(0x1001);
    address internal admin = address(0x1002);
    address internal guardian = address(0x1003);
    address internal riskManager = address(0x1004);
    address internal liquidator = address(0x1005);
    address internal factory = address(0x1006);
{asset_declaration}    function setUp() public {{
{asset_setup}        target = {constructor_call};
    }}

    function testUnauthorizedCallerMutationSurface() public {{
{setup_guard}        vm.record();
        vm.prank(attacker);
        bool ok;
        try target.{function.name}({arguments}) {{
            ok = true;
        }} catch {{
            ok = false;
        }}
        (bytes32[] memory reads, bytes32[] memory writes) = vm.accesses(address(target));
        reads;
        assertTrue(ok, "candidate call reverted; unauthorized mutation not demonstrated");
        assertGt(writes.length, 0, "candidate call did not mutate target storage");
    }}
}}
'''
    path.write_text(source, encoding="utf-8")
    return path
