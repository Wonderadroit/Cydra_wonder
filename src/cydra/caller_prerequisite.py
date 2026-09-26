from __future__ import annotations

from pathlib import Path
import re

from .foundry import generate_initialization_test
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


def _replace_initializer_call(source: str, initializer_name: str, parameter_names: tuple[str, ...]) -> tuple[str, bool]:
    pattern = re.compile(
        rf"target\.{re.escape(initializer_name)}\((?P<args>.*?)\);",
        re.DOTALL,
    )
    match = pattern.search(source)
    if match is None:
        raise ValueError(f"generated initialization test has no {initializer_name} call")
    arguments = _split_arguments(match.group("args"))
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
                arguments[index] = "CydraCallerSet.one(attacker)"
                changed = True
            elif parameter_expression.startswith(("address(", "payable(")):
                arguments[index] = "attacker"
                changed = True

    # Address arrays are the most direct generic representation of caller-role
    # membership. If the parameter name did not expose the semantic hint, do not
    # guess: the probe remains unavailable rather than inventing a setup.
    if not changed:
        for index, name in enumerate(parameter_names):
            if arguments[index].startswith("new address[]"):
                normalized = re.sub(r"[^a-z0-9]", "", name.lower())
                if any(hint in normalized for hint in _CALLER_PARAMETER_HINTS):
                    arguments[index] = "CydraCallerSet.one(attacker)"
                    changed = True
                    break

    replacement = f"target.{initializer_name}({', '.join(arguments)});"
    return source[:match.start()] + replacement + source[match.end():], changed


def _replace_test_body(source: str, initializer_name: str, target_function: str, target_arguments: tuple[str, ...]) -> str:
    marker = "function testInitializationInterfaceIsCallable() public"
    start = source.find(marker)
    if start < 0:
        raise ValueError("generated initialization test has no lifecycle test body")
    brace = source.find("{", start)
    if brace < 0:
        raise ValueError("generated initialization test lifecycle function has no body")

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

    args = ", ".join(target_arguments)
    body = (
        f"function testCallerPrerequisite() public {{\n"
        f"        target.{initializer_name}({', '.join(_initializer_arguments_from_source(source, initializer_name))});\n"
        f"        vm.prank(attacker);\n"
        f"        (bool ok,) = address(target).call(abi.encodeWithSignature(\"{target_function}({signature_types})\", {args}));\n"
        f"        assertTrue(ok, \"caller-role prerequisite was not reached after target-provided initialization\");\n"
        f"    }}"
    )
    return source[:start] + body + source[end + 1:]


def _initializer_arguments_from_source(source: str, initializer_name: str) -> list[str]:
    match = re.search(
        rf"target\.{re.escape(initializer_name)}\((?P<args>.*?)\);",
        source,
        re.DOTALL,
    )
    if match is None:
        raise ValueError(f"initializer call {initializer_name} not found")
    return _split_arguments(match.group("args"))


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
    source, changed = _replace_initializer_call(
        source,
        initializer.name,
        tuple(parameter.name for parameter in initializer.parameters),
    )
    if not changed:
        raise ValueError("initializer has no semantically identified caller-identity parameter")

    # Preserve the generated initializer call while replacing only its lifecycle
    # assertion body. This keeps constructor/interface/runtime stub generation
    # centralized in the existing initialization renderer.
    initializer_args = _initializer_arguments_from_source(source, initializer.name)
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

    target_call_arguments = ", ".join(target_args)
    body = (
        f"function testCallerPrerequisite() public {{\n"
        f"        target.{initializer.name}({', '.join(initializer_args)});\n"
        f"        vm.prank(attacker);\n"
        f"        bool ok;\n"
        f"        try target.{hypothesis.target_function}({target_call_arguments}) {{ ok = true; }} catch {{ ok = false; }}\n"
        f"        assertTrue(ok, "caller-role prerequisite was not reached after target-provided initialization");\n"
        f"    }}"
    )
    source = source[:start] + body + source[end + 1:]

    if requires_proxy_initialization(Path(contract_model.source)):
        source = adapt_generated_initialization_for_proxy(source, contract_model.name)

    helper = """
contract CydraCallerSet {
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
