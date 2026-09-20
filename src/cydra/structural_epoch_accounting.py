from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .models import ContractModel, Hypothesis, Invariant


@dataclass(frozen=True)
class EpochAccountingContribution:
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


def _constant_epoch(source: str) -> str | None:
    match = re.search(
        r"\buint\d*\s+public\s+constant\s+(?P<name>[A-Za-z_]\w*)\s*=\s*(?P<value>\d+)\s*;",
        source,
    )
    return match.group("name") if match else None


def _boundary_shape(body: str, epoch_name: str) -> bool:
    compact = re.sub(r"\s+", "", body)
    # Detect a bucket derived from i followed by a segment end expressed as
    # i + EPOCH. The two expressions are not equivalent when i is already
    # inside an epoch.
    return bool(
        re.search(
            rf"\b[A-Za-z_]\w*\s*=\([^;]*?/\b{re.escape(epoch_name)}\)\*\b{re.escape(epoch_name)}\b",
            compact,
        )
        and re.search(
            rf"\b[A-Za-z_]\w*\s*=\b[A-Za-z_]\w*\+\b{re.escape(epoch_name)}\b",
            compact,
        )
        and re.search(r"Math\.min\([^)]*,[^)]*\)-[A-Za-z_]\w*", compact),
    )


def generate_epoch_accounting_hypotheses(
    contract: ContractModel, semantic=()
) -> EpochAccountingContribution:
    source = _source(contract)
    epoch_name = _constant_epoch(source)
    if not source or epoch_name is None:
        return EpochAccountingContribution((), ())

    invariants: list[Invariant] = []
    hypotheses: list[Hypothesis] = []
    for function in contract.functions:
        if function.visibility not in {"public", "external"}:
            continue
        body = _body(source, function.name)
        if not body or not _boundary_shape(body, epoch_name):
            continue

        iid = f"INV-EPOCH-ACCOUNTING-{function.name}"
        hid = f"H-EPOCH-ACCOUNTING-{function.name}"
        invariants.append(
            Invariant(
                iid,
                "A piecewise per-epoch reward/accounting transition must use each epoch's configured rate for exactly the blocks belonging to that epoch, including when the stored start block is already inside an epoch.",
                "epoch-boundary interval partition / configured-rate conservation",
                0.86,
            )
        )
        hypotheses.append(
            Hypothesis(
                hid,
                f"{function.name} may apply one epoch's configured accounting rate across a boundary because its segment end is derived as the current position plus the full epoch size rather than the next aligned epoch boundary.",
                iid,
                function.name,
                "an external caller able to trigger the state-accounting transition after an unaligned prior checkpoint",
                "the accumulated reward/accounting state differs from the sum of the configured per-epoch rates over the actual block intervals",
                evidence_ids=(f"E-MODEL-{function.name}",),
            )
        )

    return EpochAccountingContribution(tuple(invariants), tuple(hypotheses))
