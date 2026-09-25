from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import logging
import os
import re
import subprocess
import tomllib
from typing import Literal

from .models import ContractModel, Evidence, Experiment, FunctionModel, Hypothesis, ParameterModel
from .initialization_shapes import render_initialization_test_body
from .interface_resolver import resolve_import, resolve_interface


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


def _function_argument(parameter: ParameterModel, index: int) -> str:
    """Return a conservative compile-time value for a supported ABI type.

    Authorization experiments must not invent semantics for unresolved custom
    structs/enums. Such a parameter is rejected so the caller records a
    generation capability gap instead of fabricating a potentially misleading
    experiment.
    """
    parameter_type = parameter.type.strip()
    base = parameter_type.split()[0].rstrip("[]")
    if parameter_type.endswith("[]"):
        if base.startswith(("uint", "int")) or base in {"address", "bool", "bytes32", "bytes"}:
            return f"new {base}[](0)"
        raise ValueError(f"unsupported authorization argument type: {parameter.type}")
    if parameter_type == "address payable":
        return "payable(address(0xCAFE))"
    if base == "address":
        return "address(0xCAFE)"
    if base == "bool":
        return "false"
    if base.startswith(("uint", "int")):
        return "1"
    if base == "string":
        return '"CYDRA"'
    if base == "bytes":
        return "bytes(\"\")"
    if base.startswith("bytes") and base[5:].isdigit():
        return "bytes32(uint256(1))" if base == "bytes32" else f"{base}(0x01)"
    raise ValueError(f"unsupported authorization argument type: {parameter.type}")


def generate_access_control_test(
    hypothesis: Hypothesis,
    target_import: str,
    target_type: str,
    output_path: str | Path,
    contract_model: ContractModel | None = None,
) -> Path:
    if hypothesis.invariant_id != "INV-AUTH-001":
        raise ValueError(f"Unsupported invariant for Foundry generation: {hypothesis.invariant_id}")

    if contract_model is None:
        # Preserve the legacy fixture generator for the older benchmark tests.
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

    function = next((item for item in contract_model.functions if item.name == hypothesis.target_function), None)
    if function is None:
        raise ValueError(f"Model has no target function: {hypothesis.target_function}")
    if function.visibility not in {"public", "external"}:
        raise ValueError(f"authorization target {function.name} is not externally callable")

    arguments = ", ".join(_function_argument(parameter, index) for index, parameter in enumerate(function.parameters))
    call = f"target.{function.name}({arguments});"
    pragma = contract_model.pragma or "^0.8.20"
    target_import = _layout_aware_import_path(target_import, output_path)
    return _write_test(f'''// SPDX-License-Identifier: UNLICENSED
pragma solidity {pragma};
// Hypothesis: {hypothesis.hypothesis_id}
// Structural authorization experiment: the target function and argument
// shapes come from ContractModel; no benchmark-specific function name is used.
import {{Test}} from "forge-std/Test.sol";
import {{ {target_type} }} from "{target_import}";
contract CydraAuthInvariantTest is Test {{
    {target_type} internal target;
    address internal attacker = address(0xBEEF);

    function setUp() public {{
        target = new {target_type}();
    }}

    function testUnauthorizedCallerMutationSurface() public {{
        vm.record();
        vm.prank(attacker);
        (bool ok,) = address(target).call(abi.encodeWithSignature("{function.name}({', '.join(parameter.type.split()[0] for parameter in function.parameters)})", {arguments}));
        (bytes32[] memory reads, bytes32[] memory writes) = vm.accesses(address(target));
        reads;
        assertTrue(ok, "candidate call reverted; unauthorized mutation not demonstrated");
        assertGt(writes.length, 0, "candidate call did not mutate target storage");
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
        return '""'
    if parameter_type == "bytes":
        return "bytes(\"\")"
    if parameter_type.startswith("bytes"):
        return "0"
    if parameter_type.endswith("[]"):
        return f"new {parameter_type[:-2]}[](0)"
    return "address(0)"


def _builtin_type(base: str) -> bool:
    return base in {
        "address", "bool", "string", "bytes", "byte", "uint", "int",
        *{f"uint{i}" for i in range(8, 257, 8)},
        *{f"int{i}" for i in range(8, 257, 8)},
        *{f"bytes{i}" for i in range(1, 33)},
    }


def _resolve_custom_type(parameter_type: str, target_type: str, contract_model: ContractModel) -> str:
    tokens = parameter_type.strip().split()
    if not tokens:
        return parameter_type
    type_token = tokens[0]
    base = type_token.rstrip("[]")
    if _builtin_type(base) or "." in base:
        return parameter_type

    if base in contract_model.declared_types:
        qualifier = target_type
    else:
        inherited_match = next(
            (
                interface.name
                for interface in contract_model.inherited_resolved_interfaces
                if base == interface.name or base in interface.declared_types
            ),
            None,
        )
        if inherited_match is None:
            logging.getLogger(__name__).warning(
                "unresolved custom initializer type %s on %s; emitting bare type",
                parameter_type,
                target_type,
            )
            return parameter_type
        qualifier = inherited_match

    suffix = type_token[len(base):]
    tokens[0] = f"{qualifier}.{base}{suffix}"
    return " ".join(tokens)


def _initializer_argument(
    parameter: ParameterModel,
    target_type: str,
    index: int,
    runtime_arguments: dict[str, str] | None = None,
    contract_model: ContractModel | None = None,
) -> tuple[str, str | None]:
    runtime_arguments = runtime_arguments or {}
    if parameter.name in runtime_arguments:
        return runtime_arguments[parameter.name], None
    parameter_type = parameter.type.strip()
    if parameter_type.endswith("[]"):
        base = parameter_type[:-2].strip()
        # Preserve the conservative empty boundary for primitive arrays.
        # For a source-defined struct array, provide one zero-initialized
        # element so initializers that require a non-empty collection can
        # execute without inventing target-specific field values.
        length = "1" if "." in base else "0"
        return f"new {base}[]({length})", None
    if parameter_type.startswith("address"):
        return ("payable(address(0xA11CE))" if parameter_type == "address payable" else "address(0xA11CE)"), None
    if parameter_type.startswith(("uint", "int")):
        if parameter_type.startswith("uint") and contract_model is not None:
            try:
                source = Path(contract_model.source).read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                source = ""
            if source and ("time" in parameter.name.lower() or "timestamp" in parameter.name.lower()):
                if "block.timestamp" in source:
                    epoch_match = re.search(r"%\s*(\d+)\s*==\s*0", source)
                    if epoch_match:
                        epoch = epoch_match.group(1)
                        return f"((block.timestamp / {epoch}) + 2) * {epoch}", None
        return "1", None
    if parameter_type == "bool":
        return "false", None
    if parameter_type == "string":
        return '""', None
    if parameter_type == "bytes":
        return "bytes(\"\")", None
    if parameter_type.startswith("bytes"):
        return "0", None
    variable = f"parameter{index}"
    if contract_model is None:
        declaration = f"{target_type}.{parameter_type} memory {variable};"
    else:
        qualified_type = _resolve_custom_type(parameter_type, target_type, contract_model)
        # Contract/interface types are value-like references and cannot carry
        # a data-location qualifier in a local variable declaration. Structs
        # and other reference types still require memory here.
        base_type = parameter_type.split()[0].rstrip("[]")
        interface_names = {interface.name for interface in contract_model.inherited_resolved_interfaces}
        source = _source_text(contract_model)
        is_contract_type = base_type in interface_names or bool(
            re.search(rf"\b(?:interface|contract|library)\s+{re.escape(base_type)}\b", source)
        )
        location = "" if is_contract_type else " memory"
        declaration = f"{qualified_type}{location} {variable};"
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


def _resolved_interface_import_path(source_path: str, output_path: str | Path) -> str:
    """Resolve repository-relative interface provenance against the target project root."""
    output = Path(output_path)
    project_root = next(
        (
            ancestor
            for ancestor in (output.parent, *output.parents)
            if (ancestor / "foundry.toml").exists()
        ),
        None,
    )
    raw = Path(source_path)
    if project_root is not None and not raw.is_absolute():
        candidate = project_root / raw
        if candidate.exists():
            return Path(os.path.relpath(candidate.resolve(), output.parent.resolve())).as_posix()

        # Some legacy resolver records contain an importer-relative path such
        # as Interfaces/Foo.sol. At emission time the target project root is
        # known, so resolve that already-identified file beneath contracts/
        # without guessing an interface by name or changing provenance.
        matches = sorted(
            (project_root / "contracts").rglob(raw.as_posix())
            if (project_root / "contracts").is_dir()
            else ()
        )
        if len(matches) == 1:
            return Path(os.path.relpath(matches[0].resolve(), output.parent.resolve())).as_posix()
    return _layout_aware_import_path(source_path, output_path)


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
        for receiver, parameter, method in re.findall(
            r"\b([A-Za-z_]\w*)\s*\(\s*(\w+)\s*\)\.(\w+)\s*\(",
            body,
        )
        if "ERC20" in receiver and method in {"symbol", "decimals"}
    }
    factory_context = bool(re.search(r"\b\w+\s*=\s*_msgSender\s*\(\s*\)\s*;", body)) and bool(
        re.search(r"\bIPoolFactory\s*\(\s*\w+\s*\)\s*\.\s*voter\s*\(", body)
    )
    return token_parameters, factory_context


def _semantic_override(interface_name: str, method_name: str) -> str | None:
    if interface_name == "IERC20":
        return {
            "symbol": '"CYDRA"',
            "decimals": "18",
            "approve": "true",
            "transfer": "true",
            "transferFrom": "true",
            "totalSupply": "0",
            "balanceOf": "0",
            "allowance": "0",
        }.get(method_name)
    return None


def _qualify_type(type_declaration: str, interface_name: str, known_interfaces: set[str]) -> str:
    tokens = type_declaration.strip().split()
    if not tokens:
        return type_declaration
    type_token = tokens[0]
    base = type_token.rstrip("[]")
    if _builtin_type(base):
        return type_declaration
    # Imported interface-signature symbols are top-level names in their
    # defining source. If a prior model representation qualified such a
    # symbol as Interface.Symbol, restore the compiler-valid unqualified form.
    if "." in base:
        namespace, member = base.split(".", 1)
        if member in known_interfaces:
            tokens[0] = member + ("[]" if type_token.endswith("[]") else "")
            return " ".join(tokens)
    if base not in known_interfaces and "." not in base:
        tokens[0] = f"{interface_name}.{type_token}"
    return " ".join(tokens)


def _return_declaration_with_name(return_declaration: str, index: int, interface_name: str, known_interfaces: set[str]) -> tuple[str, str]:
    tokens = return_declaration.strip().split()
    if not tokens:
        raise ValueError("Cannot generate a named return from an empty declaration")
    modifiers = {"memory", "calldata", "storage", "payable"}
    if len(tokens) > 1 and tokens[-1] not in modifiers:
        type_tokens = tokens[:-1]
    else:
        type_tokens = tokens
    type_declaration = _qualify_type(" ".join(type_tokens), interface_name, known_interfaces)
    name = f"cydraReturn{index}"
    return f"{type_declaration} {name}", name


def _stub_method_source(interface_name: str, method, derived_returns: dict[str, str], known_interfaces: set[str]) -> str:
    parameters = ", ".join(method.parameters)
    named_returns = [_return_declaration_with_name(item, index, interface_name, known_interfaces) for index, item in enumerate(method.returns)]
    returns = ", ".join(declaration for declaration, _ in named_returns)
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
    if override is not None:
        if len(named_returns) != 1:
            raise ValueError(f"Semantic override for {interface_name}.{method.name} requires one return value")
        return f"    {signature} {named_returns[0][1]} = {override}; }}"

    return f"    {signature} }}"


def _runtime_stub_source(
    resolved_interface_casts: tuple[tuple[str, object], ...],
    derived_interface_casts: tuple[tuple[str, str, object], ...],
    inherited_resolved_interfaces: tuple[object, ...],
    need_erc20: bool,
    output_path: str | Path,
) -> tuple[str, dict[str, str]]:
    resolved: dict[str, object] = {interface.name: interface for _, interface in resolved_interface_casts}
    derived_targets: dict[str, object] = {interface.name: interface for _, _, interface in derived_interface_casts}
    interfaces: dict[str, object] = dict(resolved)
    interfaces.update(derived_targets)
    known_interfaces = set(interfaces)
    for interface in interfaces.values():
        known_interfaces.update(name for name, _ in getattr(interface, "imported_types", ()))
        known_interfaces.update(getattr(interface, "top_level_types", ()))

    derived_by_source: dict[str, list[tuple[str, object]]] = {}
    for source_interface, source_method, target_interface in derived_interface_casts:
        derived_by_source.setdefault(source_interface, []).append((source_method, target_interface))
        if source_interface not in resolved:
            raise ValueError(f"Derived source interface {source_interface} is not present in resolved_interface_casts")

    variables: dict[str, str] = {}
    for interface_name in sorted(interfaces):
        variables[interface_name] = f"{interface_name[1:]}Stub"

    declarations: list[str] = []
    imported_interfaces: dict[str, object] = {}
    for interface_name, interface in sorted(interfaces.items()):
        imported_interfaces.setdefault(interface_name, interface)
        relations = derived_by_source.get(interface_name, ())
        fields = "".join(f"    address internal _cydraDerived_{method};\n" for method, _ in relations)
        constructor = ""
        if relations:
            parameters = ", ".join(f"address {method}Target" for method, _ in relations)
            assignments = " ".join(f"_cydraDerived_{method} = {method}Target;" for method, _ in relations)
            constructor = f"    constructor({parameters}) {{ {assignments} }}\n"
        derived_returns = {method: f"_cydraDerived_{method}" for method, _ in relations}
        methods = "\n".join(_stub_method_source(interface_name, method, derived_returns, known_interfaces) for method in interface.methods)
        declarations.append(
            f'''contract Cydra{interface_name}Stub {{
{fields}{constructor}{methods}
    fallback() external payable {{}}
    receive() external payable {{}}
}}'''
        )

    for interface in inherited_resolved_interfaces:
        imported_interfaces.setdefault(interface.name, interface)

    # Imported signature types (e.g. FeeTiers used by IAccountManager) need
    # their own provenance-preserving imports in the generated stub.
    imported_signature_types: dict[str, str] = {}
    for interface in imported_interfaces.values():
        for imported_name, imported_source in getattr(interface, "imported_types", ()):
            imported_signature_types.setdefault(imported_name, imported_source)
        for declared_name in getattr(interface, "top_level_types", ()):
            imported_signature_types.setdefault(declared_name, interface.source_path)

    interface_imports = [
        f'import {{ {interface_name} }} from "{_resolved_interface_import_path(interface.source_path, output_path)}";'
        for interface_name, interface in imported_interfaces.items()
    ]
    interface_imports.extend(
        f'import {{ {name} }} from "{_resolved_interface_import_path(source, output_path)}";'
        for name, source in sorted(imported_signature_types.items())
        if name not in imported_interfaces
    )

    if need_erc20:
        declarations.append('''contract CydraERC20Stub {
    function symbol() external pure returns (string memory) { return "CYDRA"; }
    function decimals() external pure returns (uint8) { return 18; }
    function approve(address, uint256) external pure returns (bool) { return true; }
    function transfer(address, uint256) external pure returns (bool) { return true; }
    function transferFrom(address, address, uint256) external pure returns (bool) { return true; }
    function totalSupply() external pure returns (uint256) { return 0; }
    function balanceOf(address) external pure returns (uint256) { return 0; }
    function allowance(address, address) external pure returns (uint256) { return 0; }
    fallback() external payable {}
    receive() external payable {}
}''')

    prefix = "\n".join(interface_imports)
    source = (prefix + "\n\n" if prefix else "") + "\n\n".join(declarations)
    return source, variables


def _model_initialization_source(
    hypothesis: Hypothesis,
    target_import: str,
    target_type: str,
    contract_model: ContractModel,
    output_path: str | Path | None = None,
    experiment: Experiment | None = None,
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
    inherited_resolved_interfaces = contract_model.inherited_resolved_interfaces
    token_parameters, factory_context = _initializer_runtime_requirements(contract_model, function.name)

    # Interface-typed initializer parameters are runtime dependencies when the
    # initializer reads ERC-20 metadata. Resolve direct parameter interfaces
    # before argument synthesis so the generic harness can bind a Cydra token
    # stub even when the concrete contract does not inherit that interface.
    parameter_interfaces = {
        interface.name: interface for interface in inherited_resolved_interfaces
    }
    if output_path is not None:
        output = Path(output_path)
        project_root = next(
            (
                ancestor
                for ancestor in (output.parent, *output.parents)
                if (ancestor / "foundry.toml").exists()
            ),
            None,
        )
        if project_root is not None:
            for parameter in function.parameters:
                base = parameter.type.strip().split()[0].rstrip("[]")
                if base in parameter_interfaces:
                    continue
                try:
                    resolved = resolve_interface(project_root, contract_model.source, base)
                except (FileNotFoundError, ValueError, OSError, UnicodeError):
                    continue
                parameter_interfaces[base] = resolved
    for parameter in function.parameters:
        base = parameter.type.strip().split()[0].rstrip("[]")
        interface = parameter_interfaces.get(base)
        if (
            (interface is not None and any(
                method.name in {"symbol", "decimals"} for method in interface.methods
            ))
            or "ERC20" in base
        ):
            # ERC20-shaped interface parameters can be backed by the canonical
            # CYDRA token stub even when the resolver cannot traverse an unusual
            # remapping in the target checkout.
            token_parameters.add(parameter.name)

    stub_source, stub_variables = _runtime_stub_source(
        resolved_interface_casts,
        derived_interface_casts,
        inherited_resolved_interfaces,
        bool(token_parameters),
        output_path or "generated.t.sol",
    )

    constructor_runtime_arguments = {
        parameter: f"address({stub_variables[interface]})"
        for parameter, interface in (constructor.interface_casts if constructor else ())
    }
    constructor_arguments = ""
    if constructor is not None and constructor.parameters:
        constructor_arguments = ", ".join(_constructor_argument(p, constructor_runtime_arguments) for p in constructor.parameters)

    initializer_runtime_arguments: dict[str, str] = {}
    for parameter in function.parameters:
        if parameter.name not in token_parameters:
            continue
        base_type = parameter.type.strip().split()[0].rstrip("[]")
        if base_type.startswith(("address", "uint", "int", "bytes", "bool", "string")):
            initializer_runtime_arguments[parameter.name] = "address(tokenStub)"
        else:
            initializer_runtime_arguments[parameter.name] = (
                f"{base_type}(address(tokenStub))"
            )
    arguments: list[str] = []
    declarations: list[str] = []
    for index, parameter in enumerate(function.parameters):
        argument, declaration = _initializer_argument(
            parameter,
            target_type,
            index,
            initializer_runtime_arguments,
            contract_model,
        )
        arguments.append(argument)
        if declaration:
            declarations.append(declaration)

    if experiment is not None and experiment.planned_inputs:
        if len(experiment.planned_inputs) != len(function.parameters):
            raise ValueError(
                f"planned input arity mismatch for {function.name}: "
                f"expected {len(function.parameters)}, got {len(experiment.planned_inputs)}"
            )
        # The canonical Experiment vector is authoritative once a safe complete
        # vector was planned. Special runtime declarations are only the fallback
        # for experiments whose planner could not safely represent the ABI inputs.
        arguments = list(experiment.planned_inputs)
        declarations = []

    initialize_args_str = ", ".join(arguments)
    test_body = render_initialization_test_body(
        function,
        target_var="target",
        unauthorized_addr="0xA11CE",
        initialize_args_str=initialize_args_str,
    )
    if declarations_text := "\n        ".join(declarations):
        opening_brace = test_body.index("{") + 1
        test_body = (
            test_body[:opening_brace]
            + "\n        "
            + declarations_text
            + "\n        "
            + test_body[opening_brace:]
        )
    pragma = contract_model.pragma or "^0.8.20"

    # Preserve source-defined custom type namespaces used by initializer
    # parameters (for example Types.StakerInfo[]) in the generated test.
    source_text = _source_text(contract_model)
    custom_namespaces = {
        parameter.type.split(".", 1)[0]
        for parameter in function.parameters
        if "." in parameter.type
    }
    # Imported interface types can appear as bare ABI parameter types (for
    # example IERC20Metadata) even when the resolver records the interface
    # itself rather than a declared struct/enum. Preserve that provenance and
    # import the exact resolved interface instead of emitting an unresolved
    # bare type into the generated harness.
    resolved_interface_names = {
        interface.name: interface for interface in contract_model.inherited_resolved_interfaces
    }
    # Resolve bare imported interface ABI types directly from the target source,
    # not only through inheritance. Initializers commonly accept an interface
    # imported by the concrete contract without inheriting it.
    direct_parameter_interfaces: dict[str, object] = {}
    project_root = None
    if output_path is not None:
        output = Path(output_path)
        project_root = next(
            (ancestor for ancestor in (output.parent, *output.parents) if (ancestor / "foundry.toml").exists()),
            None,
        )
    if project_root is not None:
        for parameter in function.parameters:
            base = parameter.type.strip().split()[0].rstrip("[]")
            if base in resolved_interface_names or _builtin_type(base) or "." in base:
                continue
            try:
                direct_parameter_interfaces[base] = resolve_interface(
                    project_root, contract_model.source, base
                )
            except (FileNotFoundError, ValueError, OSError, UnicodeError):
                continue
    for parameter in function.parameters:
        base = parameter.type.strip().split()[0].rstrip("[]")
        if base in resolved_interface_names or base in direct_parameter_interfaces:
            custom_namespaces.add(base)
            continue
        # Preserve direct source imports even when the interface resolver cannot
        # traverse an unusual remapping/alias. The source import itself is
        # authoritative provenance and avoids fabricating a bare Solidity type.
        if re.search(
            rf'import\s*\{{[^}}]*\b{re.escape(base)}\b[^}}]*\}}\s*from\s*"[^"]+"\s*;',
            source_text,
        ):
            custom_namespaces.add(base)
    custom_imports: list[str] = []
    for namespace in sorted(custom_namespaces):
        inherited_interface = resolved_interface_names.get(namespace)
        direct_interface = direct_parameter_interfaces.get(namespace)
        resolved_parameter_interface = inherited_interface or direct_interface
        if resolved_parameter_interface is not None and namespace == resolved_parameter_interface.name:
            custom_imports.append(
                f'import {{ {namespace} }} from "{_resolved_interface_import_path(resolved_parameter_interface.source_path, output_path or "generated.t.sol")}";'
            )
            continue
        match = re.search(
            rf'import\s*\{{\s*{re.escape(namespace)}\s*\}}\s*from\s*"([^"]+)"\s*;',
            source_text,
        )
        if match:
            raw_import = match.group(1)
            project_root = None
            if output_path is not None:
                output = Path(output_path)
                for ancestor in (output.parent, *output.parents):
                    if (ancestor / "foundry.toml").exists():
                        project_root = ancestor
                        break

            # ContractModel.source may be repository-relative while the generated
            # test lives under the target project. Resolve source-defined imports
            # against that project root before falling back to the legacy layout
            # resolver. This preserves provenance without emitting imports such as
            # "Interfaces/Foo.sol" relative to the project root when the real file
            # lives under contracts/Tokens/.../Interfaces.
            source_file = Path(contract_model.source)
            if not source_file.is_absolute() and project_root is not None:
                candidate_source = project_root / source_file
                if candidate_source.exists():
                    source_file = candidate_source
            source_path = source_file.parent / raw_import

            if project_root is not None and source_path.exists():
                import_path = source_path.resolve().relative_to(project_root.resolve()).as_posix()
            else:
                import_path = _layout_aware_import_path(raw_import, output_path or "generated.t.sol")
            custom_imports.append(
                f'import {{ {namespace} }} from "{import_path}";'
            )
    custom_import_text = "\n".join(custom_imports)

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
{custom_import_text}
{stub_source}
contract CydraInitializationInvariantTest is Test {{
    {target_type} internal target;
{interface_declarations}{token_declaration}{factory_method}
    function setUp() public {{
        {stub_deployments}
        {token_deployment}
        target = new {target_type}({constructor_arguments});
    }}
    {test_body}
}}
'''


def generate_initialization_test(
    hypothesis: Hypothesis,
    target_import: str,
    target_type: str,
    output_path: str | Path,
    contract_model: ContractModel | None = None,
    experiment: Experiment | None = None,
) -> Path:
    if hypothesis.invariant_id != "INV-INIT-001":
        raise ValueError(f"Unsupported invariant for Foundry generation: {hypothesis.invariant_id}")
    if experiment is not None and experiment.hypothesis_id != hypothesis.hypothesis_id:
        raise ValueError(
            f"experiment/hypothesis mismatch: {experiment.hypothesis_id} != {hypothesis.hypothesis_id}"
        )
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
        _model_initialization_source(
            hypothesis,
            target_import,
            target_type,
            contract_model,
            output_path,
            experiment,
        ),
        output_path,
    )


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
    # Some unfamiliar targets are internally valid but their default Foundry
    # compilation profile fails on unrelated stack-depth limits. Retry the
    # exact generated test with Solidity IR only when the compiler explicitly
    # reports that capability condition. This changes compiler strategy, not
    # the hypothesis, inputs, target, or blind information boundary.
    combined = f"{completed.stdout}\\n{completed.stderr}"
    if completed.returncode != 0 and "Stack too deep" in combined:
        command = ("forge", "test", "--via-ir", "--match-path", str(relative_test), "-vv")
        completed = subprocess.run(command, cwd=project, text=True, capture_output=True, check=False)
    executed, tests_run, tests_failed, status = _parse_execution(completed.stdout, completed.stderr, completed.returncode)
    return ExecutionResult(experiment_id, target, command, completed.returncode, executed, tests_run, tests_failed, status, completed.stdout, completed.stderr)


def require_executed(result: ExecutionResult) -> ExecutionResult:
    if not result.executed or result.tests_run == 0 or result.status == "UNMEASURABLE":
        stdout_tail = result.stdout[-4000:].strip()
        stderr_tail = result.stderr[-4000:].strip()
        detail = f" stdout_tail={stdout_tail!r} stderr_tail={stderr_tail!r}"
        raise RuntimeError(
            f"Foundry experiment {result.experiment_id} is UNMEASURABLE: "
            f"executed={result.executed}, tests_run={result.tests_run}, "
            f"exit_code={result.exit_code}.{detail}"
        )
    return result


def classify_experiment_outcome(
    hypothesis: Hypothesis,
    vulnerable: ExecutionResult,
    patched: ExecutionResult,
) -> ExperimentOutcome:
    """Apply the shared causal differential rule to any hypothesis class.

    Vulnerability-specific wrappers below are retained for compatibility, but
    new reasoning surfaces should use this class-neutral entry point.
    """
    return _classify(hypothesis, vulnerable, patched)


def classify_access_control_outcome(hypothesis: Hypothesis, vulnerable: ExecutionResult, patched: ExecutionResult) -> ExperimentOutcome:
    return classify_experiment_outcome(hypothesis, vulnerable, patched)


def classify_initialization_outcome(hypothesis: Hypothesis, vulnerable: ExecutionResult, patched: ExecutionResult) -> ExperimentOutcome:
    return classify_experiment_outcome(hypothesis, vulnerable, patched)


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