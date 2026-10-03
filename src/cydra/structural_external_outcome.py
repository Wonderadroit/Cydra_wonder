from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .models import ContractModel, Hypothesis, Invariant


@dataclass(frozen=True)
class ExternalOutcomeContribution:
    invariants: tuple[Invariant, ...]
    hypotheses: tuple[Hypothesis, ...]


def _source(contract: ContractModel) -> str:
    try:
        return Path(contract.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""


def _body(source: str, name: str) -> str:
    marker = re.search(
        rf"\bfunction\s+{re.escape(name)}\s*\([^)]*\)[^{{;]*\{{",
        source,
        re.S,
    )
    if not marker:
        return ""
    start = marker.end() - 1
    depth = 0
    for index in range(start, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start + 1:index]
    return ""


def _failure_capable_function_names(source: str) -> set[str]:
    """Collect explicitly boolean-returning Solidity function declarations.

    The declaration is the generic evidence that a discarded member call can
    carry a success/failure result. This works for interfaces, contracts, and
    libraries without naming a token or protocol.
    """
    names: set[str] = set()
    declaration = re.compile(
        r"\bfunction\s+(?P<name>[A-Za-z_]\w*)\s*\([^)]*\)[^{;]*?"
        r"\breturns\s*\(\s*(?:bool|bool\s+\w+)\s*\)",
        re.S,
    )
    for match in declaration.finditer(source):
        names.add(match.group("name"))
    return names


def _ignored_failure_capable_calls(source: str, body: str) -> tuple[str, ...]:
    """Find discarded external operations with an explicit failure result.

    Solidity's low-level calls are always failure-capable, while ordinary
    interface/contract calls are included only when their declaration exposes a
    boolean result. The detector therefore remains class-neutral and does not
    assume a token/protocol-specific method name.
    """
    patterns = (
        r"(?m)^\s*(?P<callee>[A-Za-z_]\w*)\s*\.\s*call(?:\s*\{[^;{}]*\})?\s*\([^;{}]*\)\s*;",
        r"(?m)^\s*(?P<callee>[A-Za-z_]\w*)\s*\.\s*delegatecall\s*\([^;{}]*\)\s*;",
        r"(?m)^\s*(?P<callee>[A-Za-z_]\w*)\s*\.\s*staticcall\s*\([^;{}]*\)\s*;",
        r"(?m)^\s*(?P<callee>[A-Za-z_]\w*)\s*\.\s*send\s*\([^;{}]*\)\s*;",
    )
    calls: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, body):
            calls.append(re.sub(r"\s+", "", match.group("callee")))

    boolean_functions = _failure_capable_function_names(source)
    member_call = re.compile(
        r"(?m)^\s*(?P<receiver>[A-Za-z_]\w*)\s*\.\s*"
        r"(?P<method>[A-Za-z_]\w*)\s*\([^;{}]*\)\s*;"
    )
    for match in member_call.finditer(body):
        method = match.group("method")
        if method in boolean_functions:
            calls.append(re.sub(r"\s+", "", match.group("receiver")) + "." + method)

    return tuple(dict.fromkeys(calls))


def generate_external_outcome_hypotheses(
    contract: ContractModel, semantic=()
) -> ExternalOutcomeContribution:
    source = _source(contract)
    if not source:
        return ExternalOutcomeContribution((), ())

    invariants: list[Invariant] = []
    hypotheses: list[Hypothesis] = []
    invariant_id = f"INV-EXTERNAL-OUTCOME-{contract.name}"
    invariant = Invariant(
        invariant_id,
        "A security- or value-relevant transition must not continue past an external operation when that operation can report failure and the result is required for the transition's correctness.",
        "external-call outcome / transition integrity",
        0.80,
    )

    for function in contract.functions:
        if function.visibility not in {"public", "external"}:
            continue
        body = _body(source, function.name)
        calls = _ignored_failure_capable_calls(source, body)
        if len(calls) < 1:
            continue
        # The structural signal is deliberately narrow: only failure-capable
        # low-level calls whose result is syntactically discarded enter this
        # surface. Execution still decides whether the result is security-relevant.
        hid = f"H-EXTERNAL-OUTCOME-{function.name}"
        hypotheses.append(
            Hypothesis(
                hid,
                f"{function.name} may continue a security- or value-relevant transition after an external call without validating the call outcome.",
                invariant_id,
                function.name,
                "external caller able to make the callee report a failure result",
                "the target performs a later state or value transition despite the external operation reporting failure",
                evidence_ids=(f"E-MODEL-{function.name}",),
            )
        )

    if hypotheses:
        invariants.append(invariant)
    return ExternalOutcomeContribution(tuple(invariants), tuple(hypotheses))
