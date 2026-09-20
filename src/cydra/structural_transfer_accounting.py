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
    for match in re.finditer(r"\.(?:safeTransferFrom|transferFrom)\s*\(", body):
        opening = body.find("(", match.start())
        depth = 0
        closing = None
        for index in range(opening, len(body)):
            if body[index] == "(":
                depth += 1
            elif body[index] == ")":
                depth -= 1
                if depth == 0:
                    closing = index
                    break
        if closing is None:
            continue
        args_text = body[opening + 1:closing]
        parts = []
        current = []
        depth = 0
        for char in args_text:
            if char in "([{":
                depth += 1
            elif char in ")]}":
                depth = max(0, depth - 1)
            if char == "," and depth == 0:
                parts.append("".join(current).strip())
                current = []
            else:
                current.append(char)
        parts.append("".join(current).strip())
        if len(parts) >= 3 and re.fullmatch(r"[A-Za-z_]\w*", parts[-1]):
            return parts[-1]
    return None

def _credits_requested_amount(body, amount, state_variables=()):
    if not amount:
        return False
    amount_name = re.escape(amount)
    direct_patterns = (
        rf"\[[^\]]+\]\s*\+=\s*{amount_name}\b",
        rf"\[[^\]]+\]\s*=\s*[^;]+\+\s*{amount_name}\b",
        rf"\b(?:total|balance|deposit|credit|shares|accounting)[A-Za-z0-9_]*\s*\+=\s*{amount_name}\b",
        rf"\b(?:total|balance|deposit|credit|shares|accounting)[A-Za-z0-9_]*\s*=\s*[^;]+\+\s*{amount_name}\b",
    )
    if any(re.search(pattern, body) for pattern in direct_patterns):
        return True

    # Track the common two-step accounting shape:
    # local = state + requestedAmount; state = local;
    # This is deliberately limited to explicit state-variable names supplied
    # by the system model and does not infer arbitrary semantics.
    aliases = {
        match.group(1)
        for match in re.finditer(
            rf"\b([A-Za-z_]\w*)\s*=\s*[^;]+\+\s*{amount_name}\b",
            body,
        )
    }
    if not aliases:
        return False
    return any(
        re.search(rf"\b{re.escape(state)}\s*=\s*{re.escape(alias)}\b", body)
        for state in state_variables
        for alias in aliases
    )

def _measures_delta(body):
    return bool(re.search(r"balanceOf\s*\(.*?\)",body) and re.search(r"(?:before|after|received|actualAmount|actual)",body,re.I))

def generate_transfer_accounting_hypotheses(contract: ContractModel, semantic=()):
    invariants=[]; hypotheses=[]
    for f in contract.functions:
        if f.visibility not in {"public","external"}: continue
        body=_body(contract,f); amount=_transfer_argument(body)
        credited = bool(amount) and (_credits_requested_amount(body, amount, contract.state_variables) or (bool(f.writes) and re.search(rf"\b{re.escape(amount)}\b", body)))
        if not body or "transferFrom" not in body or not amount or not credited or _measures_delta(body): continue
        iid=f"INV-TRANSFER-ACCOUNTING-{f.name}"
        invariants.append(Invariant(iid,"Internal credit for an inbound token transfer must equal the actual token balance delta received, not merely the requested transfer amount.","inbound transfer topology plus accounting write",0.78))
        hypotheses.append(Hypothesis(f"H-TRANSFER-ACCOUNTING-{f.name}",f"{f.name} may credit the requested token amount even when the token delivers less, allowing internal accounting to exceed assets actually received.",iid,f.name,"authorized caller able to supply a token with non-standard transfer semantics",f"recorded credit exceeds the contract's actual token balance increase after transfer",evidence_ids=(f"E-MODEL-{f.name}",)))
    return TransferAccountingContribution(tuple(invariants),tuple(hypotheses))
