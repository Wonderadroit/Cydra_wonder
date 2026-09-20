from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .models import ContractModel, Hypothesis, Invariant


@dataclass(frozen=True)
class CrossContractAttributionContribution:
    invariants: tuple[Invariant, ...]
    hypotheses: tuple[Hypothesis, ...]


def _source(contract: ContractModel) -> str:
    try:
        return Path(contract.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""


def _function_body(source: str, function_name: str, line: int) -> str | None:
    pattern = re.compile(rf"\bfunction\s+{re.escape(function_name)}\s*\([^)]*\)[^{{;]*\{{", re.S)
    for match in pattern.finditer(source):
        if source.count("\n", 0, match.start()) + 1 != line:
            continue
        start = match.end() - 1
        depth = 0
        for index in range(start, len(source)):
            if source[index] == "{":
                depth += 1
            elif source[index] == "}":
                depth -= 1
                if depth == 0:
                    return source[start + 1:index]
    return None


def _has_external_inflow_attribution_gap(body: str) -> bool:
    normalized = re.sub(r"\s+", " ", body)
    snapshot = re.search(
        r"\b(?:uint\w*\s+)?(?P<before>\w+)\s*=\s*\w+\.balanceOf\s*\(\s*address\s*\(\s*this\s*\)\s*\)\s*;",
        normalized,
    )
    transfer = re.search(r"\b\w+\.(?:safeTransferFrom|transferFrom)\s*\([^;]+\)", normalized)
    received = re.search(
        r"\b(?:uint\w*\s+)?(?P<received>\w+)\s*=\s*\w+\.balanceOf\s*\(\s*address\s*\(\s*this\s*\)\s*-\s*(?P<before>\w+)\s*;",
        normalized,
    )
    if not (snapshot and transfer and received):
        return False
    if received.group("before") != snapshot.group("before"):
        return False
    variable = received.group("received")
    subtracts_received = bool(re.search(rf"\b\w+(?:\[[^;]+\])?\s*-=\s*{re.escape(variable)}\s*;", normalized))
    if not subtracts_received:
        return False
    bounded = bool(re.search(
        rf"\b(?:min\s*\(|(?:require|assert)\s*\([^;]*\b{re.escape(variable)}\b\s*<=\s*\w+|{re.escape(variable)}\s*=\s*[^;]*\bmin\s*\()",
        normalized,
    ))
    return not bounded


def generate_cross_contract_attribution_hypotheses(
    contract: ContractModel, semantic=()
) -> CrossContractAttributionContribution:
    source = _source(contract)
    invariants: list[Invariant] = []
    hypotheses: list[Hypothesis] = []
    for function in contract.functions:
        if function.visibility not in {"public", "external"}:
            continue
        body = _function_body(source, function.name, function.line)
        if not body or not _has_external_inflow_attribution_gap(body):
            continue
        iid = f"INV-CROSS-CONTRACT-ATTRIBUTION-{function.name}"
        hid = f"H-CROSS-CONTRACT-ATTRIBUTION-{function.name}"
        invariants.append(
            Invariant(
                iid,
                "An external asset inflow used to update accounting must not attribute unrelated assets delivered during the same callback window to the caller's payment.",
                "balance-delta attribution bounded by the requested transfer",
                0.82,
            )
        )
        hypotheses.append(
            Hypothesis(
                hid,
                f"{function.name} may treat the full token balance delta as the caller's repayment even when another contract can cause additional assets to arrive during the transfer, allowing more debt to be forgiven than the requested payment.",
                iid,
                function.name,
                "the token transfer can trigger another contract path that also transfers the same asset to the receiving contract",
                "accounting reduction exceeds the caller-requested transfer amount",
                evidence_ids=(f"E-MODEL-{function.name}",),
            )
        )
    return CrossContractAttributionContribution(tuple(invariants), tuple(hypotheses))
