from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .models import ContractModel, FunctionModel, Hypothesis, Invariant


@dataclass(frozen=True)
class DoubleDebitContribution:
    invariants: tuple[Invariant, ...]
    hypotheses: tuple[Hypothesis, ...]


def _body(contract: ContractModel, function: FunctionModel) -> str:
    try:
        source = Path(contract.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""
    marker = re.search(
        rf"\bfunction\s+{re.escape(function.name)}\s*\([^)]*\)[^{{]*\{{",
        source,
    )
    if not marker:
        return ""
    start = marker.end() - 1
    depth = 0
    for i in range(start, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start + 1:i]
    return ""


def _external_value_transfer(body: str) -> bool:
    return bool(
        re.search(r"\b(?:withdraw|transfer|safeTransfer|depositAsset)\s*\(", body)
        and re.search(r"\b(?:getCollateral|getAsset|swap|execute)\s*\(", body)
    )


def _subsequent_pull(body: str) -> bool:
    return bool(
        re.search(r"\b(?:_addCollateral|_addTokens|_repay|_deposit)\s*\(", body)
        and re.search(r"\b(?:from|sender|owner|account)\b", body)
    )


def generate_double_debit_hypotheses(
    contract: ContractModel, semantic=()
) -> DoubleDebitContribution:
    """Find flows where value is already acquired by the contract then pulled again from the user."""
    invariants: list[Invariant] = []
    hypotheses: list[Hypothesis] = []

    for fn in contract.functions:
        if fn.visibility not in {"public", "external"}:
            continue
        body = _body(contract, fn)
        if not body or not _external_value_transfer(body) or not _subsequent_pull(body):
            continue
        iid = f"INV-DOUBLE-DEBIT-{fn.name}"
        invariants.append(
            Invariant(
                iid,
                "A value-acquiring operation must not charge the same economic amount twice while recording only one accounting position.",
                "fund-flow / accounting provenance topology",
                0.77,
            )
        )
        hypotheses.append(
            Hypothesis(
                f"H-DOUBLE-DEBIT-{fn.name}",
                f"{fn.name} may charge the caller twice for one accounted value because an external value transfer is followed by a second caller-funded pull of the same modeled amount.",
                iid,
                fn.name,
                "caller able to invoke the externally reachable value-acquiring operation",
                "caller loses more value than the persistent accounting position records",
                evidence_ids=(f"E-MODEL-{fn.name}",),
            )
        )
    return DoubleDebitContribution(tuple(invariants), tuple(hypotheses))
