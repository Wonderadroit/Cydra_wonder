from __future__ import annotations

from pathlib import Path
import os
import re

from .foundry import generate_initialization_test
from .experiment_inputs import _definition, _parameter_from_field, _split_fields, _type_source
from .initialization_topology import adapt_generated_initialization_for_proxy, requires_proxy_initialization
from .models import ContractModel, Experiment, Hypothesis


_CALLER_PARAMETER_HINTS = (
    "allowed",
    "allow",
    "recipient",
    "recipients",
    "caller",
    "callers",
    "account",
    "accounts",
    "user",
    "users",
    "whitelist",
    "whitelisted",
)


def _initializer_function(contract: ContractModel):
    candidates = []
    for function in (*contract.functions, *contract.inherited_functions):
        if function.visibility not in {"public", "external"}:
            continue
        modifiers = {item.lower() for item in function.modifiers}
        lifecycle = function.name.lower() in {"initialize", "initialise", "init"}
        if lifecycle or modifiers.intersection({"initializer", "reinitializer"}):
            candidates.append(function)
    return candidates[0] if candidates else None


def _split_arguments(text: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    for index, char in enumerate(text):
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(text[start:index].strip())
            start = index + 1
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def _find_initializer_call(source: str, initializer_name: str) -> tuple[int, int, str]:
    marker = f"target.{initializer_name}("
    start = source.find(marker)
    if start < 0:
        raise ValueError(f"generated initialization test has no {initializer_name} call")
    args_start = start + len(marker)
    depth = 1
    for index in range(args_start, len(source)):
        char = source[index]
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
            if depth == 0:
                terminator = re.match(r"\s*(?:;|{)", source[index + 1:])
                if terminator is None:
                    raise ValueError(
                        f"initializer call {initializer_name} is not followed by a valid Solidity call terminator"
                    )
                return start, index + 1, source[args_start:index]
    raise ValueError(f"initializer call {initializer_name} is unterminated")


def _replace_initializer_call(source: str, initializer_name: str, parameter_names: tuple[str, ...]) -> tuple[str, bool]:
    caller_variable = "cydraAttacker"
    start, end, argument_text = _find_initializer_call(source, initializer_name)
    caller_variable = "cydraAttacker"
    arguments = _split_arguments(argument_text)
    if len(arguments) != len(parameter_names):
        raise ValueError(
            f"initializer argument arity mismatch: expected {len(parameter_names)}, got {len(arguments)}"
        )

    changed = False
    for index, name in enumerate(parameter_names):
        normalized = re.sub(r"[^a-z0-9]", "", name.lower())
        if any(hint in normalized for hint in _CALLER_PARAMETER_HINTS):
            parameter_expression = arguments[index]
            if parameter_expression.startswith("new address[]"):
                arguments[index] = f"CydraCallerSet.one({caller_variable})"
                changed = True
            elif parameter_expression.startswith(("address(", "payable(")):
                arguments[index] = caller_variable
                changed = True

    if not changed:
        for index, name in enumerate(parameter_names):
            if arguments[index].startswith("new address[]"):
                normalized = re.sub(r"[^a-z0-9]", "", name.lower())
                if any(hint in normalized for hint in _CALLER_PARAMETER_HINTS):
                    arguments[index] = f"CydraCallerSet.one({caller_variable})"
                    changed = True
                    break

    # Preserve the original Solidity suffix (; for a normal call, { for a
    # try-call) instead of manufacturing a semicolon that can invalidate the
    # surrounding generated syntax.
    call_start = start
    prefix = ""
    if start >= 4 and source[start - 4:start] == "try ":
        call_start = start - 4
        prefix = "try "
    replacement = f"{prefix}target.{initializer_name}({', '.join(arguments)})"
    return source[:call_start] + replacement + source[end:], changed


def _caller_bound_initializer_arguments(
    source: str,
    initializer_name: str,
    parameter_names: tuple[str, ...],
) -> list[str]:
    """Return initializer arguments with the caller identity bound to attacker.

    This is deliberately an argument-level transformation. The generated
    lifecycle renderer may wrap its initializer call in try/catch; the caller
    prerequisite replaces that lifecycle body afterwards, so rewriting the
    renderer call itself is unnecessary and can corrupt surrounding syntax.
    """
    _, _, argument_text = _find_initializer_call(source, initializer_name)
    arguments = _split_arguments(argument_text)
    if len(arguments) != len(parameter_names):
        raise ValueError(
            f"initializer argument arity mismatch: expected {len(parameter_names)}, got {len(arguments)}"
        )

    changed = False
    for index, name in enumerate(parameter_names):
        normalized = re.sub(r"[^a-z0-9]", "", name.lower())
        if not any(hint in normalized for hint in _CALLER_PARAMETER_HINTS):
            continue
        expression = arguments[index]
        if expression.startswith("new address[]"):
            arguments[index] = "CydraCallerSet.one(attacker)"
            changed = True
        elif expression.startswith(("address(", "payable(")):
            arguments[index] = caller_variable
            changed = True

    if not changed:
        raise ValueError("initializer has no semantically identified caller-identity parameter")
    return arguments


def _initializer_arguments_from_source(source: str, initializer_name: str) -> list[str]:
    _, _, argument_text = _find_initializer_call(source, initializer_name)
    return _split_arguments(argument_text)


def _caller_role_reached(
    unauthorized_ok: bool,
    unauthorized_data: bytes,
    authorized_ok: bool,
    authorized_data: bytes,
) -> bool:
    """Determine whether the authorized call crossed the caller-authorization boundary.

    A successful authorized call proves the boundary was crossed. If the target
    later rejects the authorized call, a different revert payload from the
    unauthorized call proves execution progressed beyond the authorization
    failure. Identical revert payloads remain unresolved and fail closed.
    """
    if unauthorized_ok:
        return False
    return authorized_ok or unauthorized_data != authorized_data


def _qualify_planned_target_argument(
    parameter: object,
    expression: str,
    target_type: str,
    contract_model: ContractModel,
) -> tuple[str, set[tuple[str, str]]]:
    """Render structured values with recursive Solidity type provenance.

    Planned inputs are ABI-shaped tuples. Solidity requires every struct tuple
    at a call boundary to carry its actual struct type, including nested struct
    fields. Resolve that provenance recursively from the model's source graph;
    never invent a qualifier when the definition cannot be resolved.
    """
    imports: set[tuple[str, str]] = set()

    def render(parameter_type: str, value: str, seen: tuple[str, ...] = ()) -> str:
        parameter_type = parameter_type.strip()
        if not parameter_type or not value.lstrip().startswith("("):
            return value

        base = parameter_type.split()[0].rstrip("[]")
        if not base:
            return value

        resolved = _type_source(contract_model, base)
        if resolved is None:
            return value
        resolved_path, resolved_source = resolved
        definition = _definition(resolved_source, base)
        if definition is None or definition[0] != "struct" or base in seen:
            return value

        kind, name, body = definition
        fields = _split_fields(body)
        values = _split_arguments(value.strip()[1:-1])
        if len(fields) != len(values):
            return value

        rendered_values: list[str] = []
        for field_text, field_value in zip(fields, values):
            field = _parameter_from_field(field_text)
            if field is None:
                return value
            rendered_values.append(render(field.type, field_value, seen + (base,)))

        if base in set(contract_model.declared_types):
            qualified = f"{target_type}.{name}"
        else:
            qualified = name
            imports.add((str(resolved_path), name))
        return f"{qualified}({', '.join(rendered_values)})"

    rendered = render(getattr(parameter, "type", ""), expression)
    return rendered, imports


def _initializer_setup_declarations(source: str, initializer_name: str) -> list[str]:
    """Recover local declarations emitted by the shared initialization renderer.

    The caller-prerequisite probe reuses the renderer so custom ABI/reference
    declarations stay centralized. Those declarations originally live inside
    the generated lifecycle test and must survive when its assertion body is
    replaced by the prerequisite probe.
    """
    marker = "function testInitializationInterfaceIsCallable() public"
    function_start = source.find(marker)
    if function_start < 0:
        raise ValueError("generated initialization test lifecycle function is missing")
    brace = source.find("{", function_start)
    if brace < 0:
        raise ValueError("generated initialization test lifecycle function has no body")
    call_start, _, _ = _find_initializer_call(source, initializer_name)
    if call_start <= brace:
        return []

    prefix = source[brace + 1:call_start]
    declarations: list[str] = []
    for statement in prefix.split(";"):
        statement = statement.strip()
        if not statement:
            continue
        # Generated lifecycle probes may contain setup instrumentation before
        # the call. Keep declarations, but do not carry probe side effects into
        # the caller-role observation.
        first = statement.splitlines()[0].strip()
        # The shared initialization renderer may wrap the initializer in
        # Solidity try/catch. The token before the target call is control-flow
        # syntax, not a declaration, and must never be copied into the
        # prerequisite probe as `try;` (or an equivalent detached token).
        if first in {"try", "catch", "else", "unchecked"}:
            continue
        if first.startswith(("vm.", "assert", "target.")):
            continue
        declarations.append(statement + ";")
    return declarations


def generate_caller_prerequisite_test(
    hypothesis: Hypothesis,
    experiment: Experiment,
    target_import: str,
    target_type: str,
    output_path: str | Path,
    contract_model: ContractModel,
) -> Path:
    initializer = _initializer_function(contract_model)
    if initializer is None:
        raise ValueError("no generic initializer/reinitializer candidate is available")

    if not experiment.planned_inputs:
        raise ValueError("caller prerequisite probe requires the canonical target input vector")

    synthetic = Hypothesis(
        f"{hypothesis.hypothesis_id}-CALLER-PREREQ",
        hypothesis.claim,
        "INV-INIT-001",
        initializer.name,
        hypothesis.attacker_capability,
        hypothesis.expected_impact,
    )
    initializer_experiment = Experiment(
        synthetic.hypothesis_id,
        synthetic.hypothesis_id,
        initializer.name,
        (),
        1.0,
    )
    generated = generate_initialization_test(
        synthetic,
        target_import,
        target_type,
        output_path,
        contract_model=contract_model,
        experiment=initializer_experiment,
    )
    source = generated.read_text(encoding="utf-8")
    # Bind the caller identity directly from the renderer's argument vector.
    # Do not rewrite the renderer's call before replacing its lifecycle body:
    # a surrounding Solidity try/catch belongs to the renderer and must never
    # leak into the prerequisite probe as a detached "try;" token.
    initializer_args = _caller_bound_initializer_arguments(
        source,
        initializer.name,
        tuple(parameter.name for parameter in initializer.parameters),
    )

    setup_declarations = _initializer_setup_declarations(source, initializer.name)
    target_args = experiment.planned_inputs
    marker = "function testInitializationInterfaceIsCallable() public"
    start = source.find(marker)
    brace = source.find("{", start)
    depth = 1
    end = None
    for index in range(brace + 1, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                end = index
                break
    if end is None:
        raise ValueError("generated initialization test lifecycle function is unterminated")

    target_function = next(
        (function for function in (*contract_model.functions, *contract_model.inherited_functions)
         if function.name == hypothesis.target_function),
        None,
    )
    if target_function is None:
        raise ValueError(f"model has no target function: {hypothesis.target_function}")
    if len(target_args) != len(target_function.parameters):
        raise ValueError(
            f"target argument arity mismatch: expected {len(target_function.parameters)}, got {len(target_args)}"
        )
    typed_target_args: list[str] = []
    structured_type_imports: set[tuple[str, str]] = set()
    for parameter, expression in zip(target_function.parameters, target_args):
        rendered, imports = _qualify_planned_target_argument(
            parameter, expression, target_type, contract_model
        )
        typed_target_args.append(rendered)
        structured_type_imports.update(imports)
    target_call_arguments = ", ".join(typed_target_args)
    declarations_text = "".join(f"        {item}\n" for item in setup_declarations)
    target_call_data = f"abi.encodeCall(target.{hypothesis.target_function}, ({target_call_arguments}))"
    body = (
        f"function testCallerPrerequisite() public {{\n"
        f"        address cydraAttacker = address(0xBEEF);\n"
        f"        address cydraUnauthorized = address(0xA11CE);\n"
        f"{declarations_text}"
        f"        target.{initializer.name}({', '.join(initializer_args)});\n"
        f"        vm.prank(cydraUnauthorized);\n"
        f"        (bool unauthorizedOk, bytes memory unauthorizedData) = address(target).call({target_call_data});\n"
        f'        assertFalse(unauthorizedOk, "caller-role prerequisite was not enforced for an unauthorized caller");\n'
        f"        vm.prank(cydraAttacker);\n"
        f"        (bool authorizedOk, bytes memory authorizedData) = address(target).call({target_call_data});\n"
        f"        bool callerRoleReached = authorizedOk || keccak256(authorizedData) != keccak256(unauthorizedData);\n"
        f'        assertTrue(callerRoleReached, "caller-role prerequisite was not reached after target-provided initialization");\n'
        f"    }}"
    )
    source = source[:start] + body + source[end + 1:]

    if requires_proxy_initialization(Path(contract_model.source)):
        source = adapt_generated_initialization_for_proxy(source, contract_model.name)

    if structured_type_imports:
        output_file = Path(generated)
        import_lines = []
        for import_source, type_name in sorted(structured_type_imports):
            relative = Path(os.path.relpath(
                Path(import_source).resolve(),
                output_file.parent.resolve(),
            )).as_posix()
            import_lines.append(f'import {{ {type_name} }} from "{relative}";')
        source = source.replace(
            f'import {{ {target_type} }} from "',
            "\n".join(import_lines) + "\n" + f'import {{ {target_type} }} from "',
            1,
        )

    helper = """
library CydraCallerSet {
    function one(address caller) internal pure returns (address[] memory callers) {
        callers = new address[](1);
        callers[0] = caller;
    }
}
"""
    marker = f"contract CydraInitializationInvariantTest is Test {{"
    if "contract CydraCallerSet" not in source:
        source = source.replace(marker, helper + "\n" + marker, 1)

    generated.write_text(source, encoding="utf-8")
    return generated
