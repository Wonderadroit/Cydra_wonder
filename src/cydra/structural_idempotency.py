from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .models import ContractModel, FunctionModel, Hypothesis, Invariant


@dataclass(frozen=True)
class IdempotencyContribution:
    invariants: tuple[Invariant, ...]
    hypotheses: tuple[Hypothesis, ...]


def _body(contract: ContractModel, function: FunctionModel) -> str:
    try:
        source = Path(contract.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""
    marker = re.search(rf"\bfunction\s+{re.escape(function.name)}\s*\([^)]*\)[^{{]*\{{", source)
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


def _has_status_assignment(body: str) -> bool:
    return bool(re.search(r"\.[A-Za-z_]\w*\s*=\s*[A-Za-z_]\w*", body))


def _has_value_transfer(body: str) -> bool:
    return bool(re.search(r"\.(?:transfer|safeTransfer|transferFrom)\s*\(", body))


def _has_repeated_input_loop(body: str) -> bool:
    return bool(re.search(r"\bfor\s*\([^)]*;[^)]*;[^)]*\)", body)) and bool(
        re.search(r"\[[^\]]+\]", body)
    )


def _has_pre_state_guard(body: str) -> bool:
    return bool(
        re.search(
            r"\brequire\s*\([^)]*(?:status|state|decision|processed|used|claimed|executed|consumed|cancel)[^)]*(?:==|!=)[^)]*\)",
            body,
            flags=re.IGNORECASE,
        )
    )


def generate_idempotency_hypotheses(
    contract: ContractModel, semantic=()
) -> IdempotencyContribution:
    """Find state-changing batch transitions that can consume the same record repeatedly.

    The detector observes a topology: a user-controlled repeated-input loop mutates
    per-record state and performs a value transfer, without an observed pre-state guard.
    It does not encode a target, function name, exploit amount, or historical answer.
    """
    invariants: list[Invariant] = []
    hypotheses: list[Hypothesis] = []
    for function in contract.functions:
        if function.visibility not in {"public", "external"} or not function.writes:
            continue
        body = _body(contract, function)
        if not (_has_repeated_input_loop(body) and _has_status_assignment(body) and _has_value_transfer(body)):
            continue
        if _has_pre_state_guard(body):
            continue

        iid = f"INV-IDEMPOTENCY-{function.name}"
        invariants.append(
            Invariant(
                iid,
                "A stateful value-releasing transition should not consume the same record more than once without a valid new pre-state.",
                "record lifecycle / one-time transition topology",
                0.76,
            )
        )
        hypotheses.append(
            Hypothesis(
                f"H-IDEMPOTENCY-{function.name}",
                f"{function.name} may process the same state record repeatedly because the transition lacks an observed pre-state guard before the value-releasing side effect.",
                iid,
                function.name,
                "authorized external caller able to supply repeated record identifiers",
                "the same record can trigger the value-releasing transition more than once",
                evidence_ids=(f"E-MODEL-{function.name}",),
            )
        )

    return IdempotencyContribution(tuple(invariants), tuple(hypotheses))
