from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .models import ContractModel, Hypothesis, Invariant


@dataclass(frozen=True)
class CallbackStateOrderContribution:
    invariants: tuple[Invariant, ...]
    hypotheses: tuple[Hypothesis, ...]


def _body(contract: ContractModel, function) -> str:
    try:
        source = Path(contract.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""
    marker = re.search(rf"\\bfunction\\s+{re.escape(function.name)}\\s*\\([^)]*\\)[^{{;]*\\{{", source, re.S)
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


def _external_value_transfer(body: str) -> bool:
    return bool(re.search(r"(?:\\.call\\s*\\{\\s*value\\s*:|\\.transfer\\s*\\(|\\.send\\s*\\(|\\.safeTransferETH\\s*\\()", body))


def _state_write_after_external_transfer(body: str) -> bool:
    transfer = re.search(r"(?:\\.call\\s*\\{\\s*value\\s*:|\\.transfer\\s*\\(|\\.send\\s*\\(|\\.safeTransferETH\\s*\\()", body)
    if not transfer:
        return False
    tail = body[transfer.end():]
    return bool(re.search(r"\\b[A-Za-z_]\\w*(?:\\s*\\[[^\\]]+\\])*\\s*(?:=|\\+=|-=|\\*=|/=|%=|\\+\\+|--)", tail))


def generate_callback_state_order_hypotheses(contract: ContractModel, semantic=()) -> CallbackStateOrderContribution:
    invariants: list[Invariant] = []
    hypotheses: list[Hypothesis] = []
    public_functions = [f for f in contract.functions if f.visibility in {"public", "external"}]

    for function in contract.functions:
        body = _body(contract, function)
        if not body or not _external_value_transfer(body) or not _state_write_after_external_transfer(body):
            continue

        if function.visibility not in {"public", "external"}:
            callers = [f for f in public_functions if re.search(rf"\\b{re.escape(function.name)}\\s*\\(", _body(contract, f))]
            if not callers:
                continue
            target = callers[0]
        else:
            target = function

        if not target.writes:
            continue

        iid = f"INV-CALLBACK-STATE-ORDER-{target.name}"
        invariants.append(Invariant(
            iid,
            "Security-critical state establishing a temporal or authorization condition must be updated before an externally observable value transfer can invoke attacker-controlled code.",
            "external callback topology plus state-write ordering",
            0.60,
        ))
        hypotheses.append(Hypothesis(
            f"H-CALLBACK-STATE-ORDER-{target.name}",
            f"{target.name} may expose an intermediate state during an external value transfer, allowing a reentrant caller to bypass a state-dependent condition before the condition is recorded.",
            iid,
            target.name,
            "a caller-controlled contract able to receive a value-transfer callback and reenter the target",
            f"a reentrant call can exploit the pre-update state while {function.name} is still executing",
            evidence_ids=(f"E-MODEL-{target.name}",),
        ))

    return CallbackStateOrderContribution(tuple(invariants), tuple(hypotheses))
