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


def _standalone_external_calls(body: str) -> tuple[str, ...]:
    calls: list[str] = []
    for match in re.finditer(
        r"(?m)^\s*(?P<callee>[A-Za-z_]\w*(?:\s*\.\s*[A-Za-z_]\w+)?)\s*\([^;{}]*\)\s*;",
        body,
    ):
        callee = re.sub(r"\s+", "", match.group("callee"))
        if "." in callee:
            calls.append(callee)
    return tuple(calls)


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
        calls = _standalone_external_calls(body)
        if len(calls) < 1:
            continue
        # The structural signal is deliberately conservative: a standalone
        # external call is a candidate for ignored-result semantics. Execution
        # decides whether its return value is actually security-relevant.
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
