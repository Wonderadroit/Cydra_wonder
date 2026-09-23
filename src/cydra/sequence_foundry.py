from __future__ import annotations

from pathlib import Path
import os

from .models import ContractModel, Experiment, Hypothesis
from .interface_resolver import resolve_interface, resolve_named_type_source
from .execution_readiness import _address_role, caller_role, inspect_execution_readiness
from .experiment_inputs import conservative_defaults


def generate_sequence_test_from_experiment(
    hypothesis: Hypothesis,
    experiment: Experiment,
    target_import: str,
    target_type: str,
    output_path: str | Path,
    contract_model: ContractModel,
) -> Path:
    """Render a structured ordered experiment into an executable Foundry test.

    This renderer knows only the generic ExperimentStep envelope. It does not
    inspect invariant IDs or vulnerability classes. A step must name an
    externally callable modeled function and provide an argument vector whose
    arity matches that function.
    """
    if experiment.hypothesis_id != hypothesis.hypothesis_id:
        raise ValueError(
            f"experiment/hypothesis mismatch: {experiment.hypothesis_id} != {hypothesis.hypothesis_id}"
        )
    if not experiment.steps:
        raise ValueError("sequence experiment has no structured steps")

    functions = {function.name: function for function in contract_model.functions}
    rendered: list[str] = []
    role_addresses = {"owner": "address(0x1001)", "admin": "address(0x1002)", "guardian": "address(0x1003)", "risk_manager": "address(0x1004)", "liquidator": "address(0x1005)", "factory": "address(0x1006)"}
    functions_by_name = {function.name: function for function in contract_model.functions}
    caller_bindings = {"owner": "owner", "admin": "admin", "guardian": "guardian", "risk_manager": "riskManager", "liquidator": "liquidator", "factory": "factory"}
    setup_keys: set[str] = set()
    setup_rendered: list[str] = []
    for index, step in enumerate(experiment.steps):
        if not step.function.strip():
            raise ValueError(f"sequence step {index} has no function")
        function = functions.get(step.function)
        if function is None:
            raise ValueError(f"model has no sequence function: {step.function}")
        if function.visibility not in {"public", "external"}:
            raise ValueError(f"sequence function is not externally callable: {step.function}")
        if len(step.arguments) != len(function.parameters):
            raise ValueError(
                f"sequence input arity mismatch for {step.function}: "
                f"expected {len(function.parameters)}, got {len(step.arguments)}"
            )
        if any(not argument.strip() for argument in step.arguments):
            raise ValueError(f"sequence step {step.function} contains an empty argument")
        arguments = ", ".join(step.arguments)
        readiness = inspect_execution_readiness(contract_model, function)
        for requirement in readiness.state_setup_candidates:
            if requirement.status != "constructible" or requirement.subject in setup_keys:
                continue
            writer = functions_by_name.get(requirement.subject)
            if writer is None:
                continue
            defaults = conservative_defaults(writer.parameters)
            if defaults is None:
                continue
            writer_args = ", ".join(defaults.get(parameter.name, "") for parameter in writer.parameters)
            if any(not value for value in defaults.values()):
                continue
            writer_role = caller_bindings.get(caller_role(writer), "attacker")
            setup_rendered.append(f"        vm.prank({writer_role});\\n        target.{writer.name}({writer_args});")
            setup_keys.add(requirement.subject)
        role = caller_role(function)
        caller_bindings = {"owner": "owner", "admin": "admin", "guardian": "guardian", "risk_manager": "riskManager", "liquidator": "liquidator", "factory": "factory"}
        caller = caller_bindings.get(role, "attacker") if role else "attacker"
        rendered.append(f"        vm.prank({caller});\n        target.{step.function}({arguments});")

    pragma = contract_model.pragma or "^0.8.20"
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Constructor-aware deployment is part of the generic sequence renderer.
    # A target with a non-empty constructor must be instantiated with a
    # compiler-valid argument vector; otherwise Foundry reports an opaque
    # struct-constructor error before the actual experiment can execute.
    constructor_arguments: list[str] = []
    constructor_imports: list[str] = []
    project_root = next(
        (ancestor for ancestor in (path.parent, *path.parents) if (ancestor / "foundry.toml").exists()),
        None,
    )
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
            raise ValueError(f"unsupported sequence constructor array type: {parameter.type}")
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
            constructor_imports.append(
                f'import {{ {base} }} from "{Path(os.path.relpath(project_root / resolved.source_path, path.parent)).as_posix()}";'
            )
        elif base in named_type_sources:
            if base == "ERC20":
                erc20_stub_needed = True
                constructor_arguments.append("ERC20(address(constructorAsset))")
            else:
                constructor_arguments.append(f"{base}(address(0))")
            resolved_path = Path(project_root / named_type_sources[base])
            relative = Path(os.path.relpath(resolved_path, path.parent)).as_posix()
            constructor_imports.append(f'import {{ {base} }} from "{relative}";')
        elif "." in base:
            raise ValueError(f"unsupported sequence constructor namespaced type: {parameter.type}")
        else:
            raise ValueError(f"unsupported sequence constructor type: {parameter.type}")

    constructor_args_text = ", ".join(constructor_arguments)
    constructor_call = f"new {target_type}({constructor_args_text})" if constructor_arguments else f"new {target_type}()"
    import_text = "\n".join(dict.fromkeys(constructor_imports))

    stub_declaration = (
        'contract CydraERC20ConstructorStub is ERC20 { constructor() ERC20("CYDRA", "CYDRA", 18) {} }\n'
        if erc20_stub_needed else ""
    )
    asset_declaration = "    ERC20 internal constructorAsset;\n" if erc20_stub_needed else ""
    asset_setup = "        constructorAsset = new CydraERC20ConstructorStub();\n" if erc20_stub_needed else ""
    rendered.insert(0, "\n".join(setup_rendered))
    source = f'''// SPDX-License-Identifier: UNLICENSED
pragma solidity {pragma};
// Hypothesis: {hypothesis.hypothesis_id}
// Experiment: {experiment.experiment_id}
// Structured ordered steps are authoritative for this execution.
import {{Test}} from "forge-std/Test.sol";
import {{ {target_type} }} from "{target_import}";
{import_text}

{stub_declaration}contract CydraSequenceExperimentTest is Test {{
    {target_type} internal target;
    address internal attacker = address(0xBEEF);\n    address internal owner = address(0x1001);\n    address internal admin = address(0x1002);\n    address internal guardian = address(0x1003);\n    address internal riskManager = address(0x1004);\n    address internal liquidator = address(0x1005);\n    address internal factory = address(0x1006);
{asset_declaration}    function setUp() public {{
{asset_setup}        target = {constructor_call};
    }}

    function testOrderedExperimentSequence() public {{
{chr(10).join(rendered)}
    }}
}}
'''
    path.write_text(source, encoding="utf-8")
    return path
