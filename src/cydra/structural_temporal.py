from __future__ import annotations
from pathlib import Path
from dataclasses import dataclass
import re
from .models import ContractModel, Hypothesis, Invariant
@dataclass(frozen=True)
class TemporalPreconditionContribution:
    invariants: tuple[Invariant, ...]
    hypotheses: tuple[Hypothesis, ...]
def _body(contract, function):
    try: source=Path(contract.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError): return ""
    marker=re.search(rf"\bfunction\s+{re.escape(function.name)}\s*\([^)]*\)[^{{]*\{{",source)
    if not marker:return ""
    start=marker.end()-1;depth=0
    for i in range(start,len(source)):
        if source[i]=='{':depth+=1
        elif source[i]=='}':
            depth-=1
            if depth==0:return source[start+1:i]
    return ""
def generate_temporal_precondition_hypotheses(contract, semantic=()):
    inv=[];hyps=[]
    for f in contract.functions:
        if f.visibility not in {"public","external"} or not f.writes:continue
        body=_body(contract,f)
        call_positions=[m.start() for m in re.finditer(r"\bthis\.\w+\s*\(",body)]
        call_positions += [m.start() for m in re.finditer(r"\b(?:call|_call|_execute|executeCall|externalCall)\s*\(",body)]
        if not call_positions:continue
        first_call=min(call_positions)
        lower=body.lower()
        if "require(" not in lower and "assert(" not in lower:continue
        check_positions=[p for p in (lower.find("require(",first_call),lower.find("assert(",first_call)) if p>=0]
        if not check_positions:continue
        iid=f"INV-TEMPORAL-PRECONDITION-{f.name}"
        inv.append(Invariant(iid,"Security-relevant preconditions should be established before external state-changing calls when those calls can alter the predicate being checked.","call-order / precondition topology",0.72))
        hyps.append(Hypothesis(f"H-TEMPORAL-{f.name}",f"{f.name} may make an external state-changing call before checking a security-relevant precondition, allowing the call sequence to change the predicate and satisfy it retroactively.",iid,f.name,"authorized external caller able to reach the transition","a precondition that should constrain entry can become true during the transition",evidence_ids=(f"E-MODEL-{f.name}",)))
    return TemporalPreconditionContribution(tuple(inv),tuple(hyps))
