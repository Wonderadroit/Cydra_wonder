from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import re
from .models import ContractModel, Hypothesis, Invariant

@dataclass(frozen=True)
class TransferAccountingContribution:
    invariants: tuple[Invariant, ...]
    hypotheses: tuple[Hypothesis, ...]

def _body(contract, function):
    try: source=Path(contract.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError): return ""
    m=re.search(rf"\bfunction\s+{re.escape(function.name)}\s*\([^)]*\)[^{{]*\{{",source)
    if not m: return ""
    start=m.end()-1; depth=0
    for i in range(start,len(source)):
        if source[i]=="{": depth+=1
        elif source[i]=="}":
            depth-=1
            if depth==0: return source[start+1:i]
    return ""

def _transfer_argument(body):
    m=re.search(r"\.transferFrom\s*\(\s*[^,]+\s*,\s*[^,]+\s*,\s*([A-Za-z_]\w*)\s*\)",body)
    return m.group(1) if m else None

def _credits_requested_amount(body, amount):
    if not amount: return False
    patterns=(rf"\[[^\]]+\]\s*\+=\s*{re.escape(amount)}\b",rf"\[[^\]]+\]\s*=\s*[^;]+\+\s*{re.escape(amount)}\b",rf"\b(?:total|balance|deposit|credit|shares|accounting)[A-Za-z0-9_]*\s*\+=\s*{re.escape(amount)}\b",rf"\b(?:total|balance|deposit|credit|shares|accounting)[A-Za-z0-9_]*\s*=\s*[^;]+\+\s*{re.escape(amount)}\b")
    return any(re.search(p,body) for p in patterns)

def _measures_delta(body):
    return bool(re.search(r"balanceOf\s*\(.*?\)",body) and re.search(r"(?:before|after|received|actualAmount|actual)",body,re.I))

def generate_transfer_accounting_hypotheses(contract: ContractModel, semantic=()):
    invariants=[]; hypotheses=[]
    for f in contract.functions:
        if f.visibility not in {"public","external"}: continue
        body=_body(contract,f); amount=_transfer_argument(body)
        if not body or "transferFrom" not in body or not amount or not _credits_requested_amount(body,amount) or _measures_delta(body): continue
        iid=f"INV-TRANSFER-ACCOUNTING-{f.name}"
        invariants.append(Invariant(iid,"Internal credit for an inbound token transfer must equal the actual token balance delta received, not merely the requested transfer amount.","inbound transfer topology plus accounting write",0.78))
        hypotheses.append(Hypothesis(f"H-TRANSFER-ACCOUNTING-{f.name}",f"{f.name} may credit the requested token amount even when the token delivers less, allowing internal accounting to exceed assets actually received.",iid,f.name,"authorized caller able to supply a token with non-standard transfer semantics",f"recorded credit exceeds the contract's actual token balance increase after transfer",evidence_ids=(f"E-MODEL-{f.name}",)))
    return TransferAccountingContribution(tuple(invariants),tuple(hypotheses))
