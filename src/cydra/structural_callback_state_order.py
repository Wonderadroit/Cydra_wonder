from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .models import ContractModel, Hypothesis, Invariant


@dataclass(frozen=True)
class CallbackStateOrderContribution:
    invariants: tuple[Invariant, ...]
    hypotheses: tuple[Hypothesis, ...]


_FUNCTION_RE = re.compile(
    r"\bfunction\s+(?P<name>\w+)\s*\((?P<params>[^)]*)\)\s*(?P<tail>[^\{;]*)\{",
    re.MULTILINE,
)

_EXTERNAL_INTERACTION_RE = re.compile(
    r"(?:"
    r"\.call\s*\{\s*value\s*:"
    r"|\.transfer\s*\("
    r"|\.send\s*\("
    r"|\.safeTransferETH\s*\("
    r"|\b[A-Za-z_]\w*\s*\.\s*[A-Za-z_]\w*\s*\("
    r")"
)


def _source(contract: ContractModel) -> str:
    try:
        return Path(contract.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""


def _function_body(source: str, match: re.Match[str]) -> str:
    start = match.end() - 1
    depth = 0
    for index in range(start, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start + 1:index]
    return ""


def _external_interaction(body: str) -> re.Match[str] | None:
    return _EXTERNAL_INTERACTION_RE.search(body)


def _state_write_after_external_interaction(body: str, interaction: re.Match[str]) -> bool:
    tail = body[interaction.end():]
    return bool(re.search(
        r"\b[A-Za-z_]\w*(?:\s*\[[^\]]+\])*\s*(?:=|\+=|-=|\*=|/=|%=|\+\+|--)",
        tail,
    ))


def _public_callers(function_name: str, functions: tuple[tuple[str, str, str], ...]) -> tuple[str, ...]:
    return tuple(
        name
        for name, tail, body in functions
        if re.search(r"\b(?:public|external)\b", tail)
        and re.search(rf"\b{re.escape(function_name)}\s*\(", body)
    )


def generate_callback_state_order_hypotheses(contract: ContractModel, semantic=()) -> CallbackStateOrderContribution:
    source = _source(contract)
    if not source:
        return CallbackStateOrderContribution((), ())

    parsed: list[tuple[str, str, str]] = []
    for match in _FUNCTION_RE.finditer(source):
        parsed.append((match.group("name"), match.group("tail"), _function_body(source, match)))

    public_names = {
        name for name, tail, _body in parsed
        if re.search(r"\b(?:public|external)\b", tail)
    }

    invariants: list[Invariant] = []
    hypotheses: list[Hypothesis] = []
    seen: set[str] = set()

    for function_name, tail, body in parsed:
        interaction = _external_interaction(body)
        if not body or interaction is None or not _state_write_after_external_interaction(body, interaction):
            continue

        if function_name in public_names:
            target = function_name
        else:
            callers = _public_callers(function_name, tuple(parsed))
            if not callers:
                continue
            target = callers[0]

        hypothesis_id = f"H-CALLBACK-STATE-ORDER-{target}"
        if hypothesis_id in seen:
            continue
        seen.add(hypothesis_id)

        invariant_id = f"INV-CALLBACK-STATE-ORDER-{target}"
        invariants.append(Invariant(
            invariant_id,
            "Security-critical state establishing a temporal or authorization condition must be updated before an external interaction can invoke attacker-controlled code.",
            "external interaction topology plus state-write ordering",
            0.80,
        ))
        hypotheses.append(Hypothesis(
            hypothesis_id,
            f"{target} may expose an intermediate state during an external interaction, allowing a reentrant caller to bypass a state-dependent condition before the condition is recorded.",
            invariant_id,
            target,
            "a caller-controlled contract able to execute during an external interaction and reenter the target",
            f"a reentrant call can exploit the pre-update state while {function_name} is still executing",
            evidence_ids=(f"E-MODEL-{target}",),
            related_functions=(function_name,) if function_name != target else (),
        ))

    return CallbackStateOrderContribution(tuple(invariants), tuple(hypotheses))
