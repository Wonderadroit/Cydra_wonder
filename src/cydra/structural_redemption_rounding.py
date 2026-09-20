from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import re
from .models import ContractModel, Hypothesis, Invariant

@dataclass(frozen=True)
class RedemptionRoundingContribution:
    invariants: tuple[Invariant, ...]
    hypotheses: tuple[Hypothesis, ...]

def _body(contract, function):
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

def _has_exchange_rate_state(body: str) -> bool:
    return bool(re.search(r"\bexchangeRate\b", body)) and bool(re.search(r"\btotalSupply\b", body))

def _rounds_down_required_shares(body: str) -> bool:
    if not re.search(r"\bredeemTokens\s*=\s*[^;]+/\s*exchangeRate\b", body):
        return False
    return not bool(re.search(r"\+\s*exchangeRate\s*-\s*1\s*\)\s*/\s*exchangeRate\b", body))

def _has_asset_release(body: str) -> bool:
    return bool(re.search(r"\b(?:cash|assets?|underlying)[A-Za-z0-9_]*\s*-=", body)) or bool(
        re.search(r"\.(?:transfer|safeTransfer)\s*\(", body)
    )

def generate_redemption_rounding_hypotheses(contract: ContractModel, semantic=()):
    invariants=[]; hypotheses=[]
    for function in contract.functions:
        if function.visibility not in {"public","external"} or function.name.lower() not in {"redeemunderlying","withdraw"}:
            continue
        body=_body(contract,function)
        if not body or not _has_exchange_rate_state(body) or not _rounds_down_required_shares(body) or not _has_asset_release(body):
            continue
        iid=f"INV-REDEMPTION-ROUNDING-{function.name}"
        invariants.append(Invariant(
            iid,
            "When a transition computes the shares or receipt units required to withdraw a requested asset amount, the required share burn must not round down.",
            "exchange-rate conversion plus asset release and conservative redemption accounting",
            0.78,
        ))
        hypotheses.append(Hypothesis(
            f"H-REDEMPTION-ROUNDING-{function.name}",
            f"{function.name} may round the required share burn down, allowing a caller to withdraw the requested assets while surrendering fewer receipt units than the exchange rate requires.",
            iid,
            function.name,
            "caller able to reach a fractional asset-to-share conversion boundary",
            "observed receipt-unit burn is below the mathematical ceiling required for the requested asset withdrawal",
            evidence_ids=(f"E-MODEL-{function.name}",),
        ))
    return RedemptionRoundingContribution(tuple(invariants),tuple(hypotheses))
