from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import re

from .models import ContractModel, Hypothesis, Invariant

@dataclass(frozen=True)
class CrossContractEconomicContribution:
    invariants: tuple[Invariant, ...]
    hypotheses: tuple[Hypothesis, ...]

def _source(contract: ContractModel) -> str:
    try:
        return Path(contract.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""

def _contract_blocks(source: str):
    pattern = re.compile(r"\bcontract\s+(\w+)\s*\{")
    for m in pattern.finditer(source):
        depth = 0
        end = None
        for i in range(m.end()-1, len(source)):
            if source[i] == "{": depth += 1
            elif source[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end is not None:
            yield m.group(1), source[m.start():end+1]

def _has_cross_contract_report_gap(source: str) -> tuple[str, str] | None:
    blocks = dict(_contract_blocks(source))
    for vault_name, body in blocks.items():
        call = re.search(r"\b(\w+)\s+reported\s*=\s*(\w+)\.\w+\s*\(([^;]*)\)\s*;\s*(?:accountedAssets|totalAssets|assets)\s*\+=\s*reported\s*;", body, re.S)
        if not call:
            continue
        callee = call.group(2)
        callee_body = blocks.get(callee, "")
        if not callee_body:
            continue
        if re.search(r"\buint\w*\s+delivered\s*=\s*[^;]+;\s*[^;]*\.transfer\s*\([^;]*delivered[^;]*\)\s*;\s*return\s+\w+\s*;", callee_body, re.S):
            if re.search(r"\breturn\s+\w+\s*;", callee_body):
                return vault_name, callee
    return None

def generate_cross_contract_economic_hypotheses(contract: ContractModel, semantic=()):
    source = _source(contract)
    gap = _has_cross_contract_report_gap(source)
    if not gap:
        return CrossContractEconomicContribution((), ())
    vault_name, callee = gap
    target = next((f for f in contract.functions if f.name.lower().startswith("sync") or f.name.lower().startswith("harvest")), None)
    if target is None:
        return CrossContractEconomicContribution((), ())
    iid=f"INV-CROSS-CONTRACT-ECONOMIC-{target.name}"
    hid=f"H-CROSS-CONTRACT-ECONOMIC-{target.name}"
    invariant=Invariant(
        iid,
        "A system's internal asset accounting must not increase by more than the assets actually delivered across a cross-contract boundary.",
        "cross-contract reported-value flow versus delivered-asset flow",
        0.80,
    )
    hypothesis=Hypothesis(
        hid,
        f"{target.name} may trust a cross-contract reported asset amount that exceeds the assets actually delivered, allowing internal accounting to become economically unbacked.",
        iid,
        target.name,
        "callee reports an amount different from the asset amount actually delivered",
        "internal accounted assets exceed the receiving contract's actual asset balance after synchronization",
        evidence_ids=(f"E-CROSS-CONTRACT-{vault_name}-{callee}",),
    )
    return CrossContractEconomicContribution((invariant,), (hypothesis,))
