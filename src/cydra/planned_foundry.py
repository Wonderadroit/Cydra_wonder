from __future__ import annotations

from pathlib import Path
from .interface_resolver import resolve_interface, resolve_named_type_source

from .models import ContractModel, Experiment, Hypothesis
from .planned_call import render_function_call


def generate_authorization_test_from_experiment(
    hypothesis: Hypothesis,
    experiment: Experiment,
    target_import: str,
    target_type: str,
    output_path: str | Path,
    contract_model: ContractModel,
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
    constructor_arguments: list[str] = []
    constructor_imports: list[str] = []
    inherited_interfaces = {item.name: item for item in contract_model.inherited_resolved_interfaces}
    direct_interfaces: dict[str, object] = {}
    named_type_sources: dict[str, str] = {}
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
            constructor_arguments.append("address(0)")
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
            constructor_arguments.append(f"{base}(address(0))")
            resolved_path = Path(project_root / named_type_sources[base])
            relative = Path(__import__("os").path.relpath(resolved_path, path.parent)).as_posix()
            constructor_imports.append(f'import {{ {base} }} from "{relative}";')
        else:
            raise ValueError(f"unsupported authorization constructor type: {parameter.type}")

    constructor_args_text = ", ".join(constructor_arguments)
    constructor_call = f"new {target_type}({constructor_args_text})" if constructor_arguments else f"new {target_type}()"
    constructor_import_text = "\n".join(dict.fromkeys(constructor_imports))

    source = f'''// SPDX-License-Identifier: UNLICENSED
pragma solidity {pragma};
// Hypothesis: {hypothesis.hypothesis_id}
// Experiment: {experiment.experiment_id}
// Planned inputs are authoritative for this concrete target call.
import {{Test}} from "forge-std/Test.sol";
import {{ {target_type} }} from "{target_import}";
{constructor_import_text}

contract CydraAuthInvariantTest is Test {{
    {target_type} internal target;
    address internal attacker = address(0xBEEF);

    function setUp() public {{
        target = {constructor_call};
    }}

    function testUnauthorizedCallerMutationSurface() public {{
        vm.record();
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
