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
    marker=re.search(rf"\\bfunction\\s+{re.escape(function.name)}\\s*\\([^)]*\\)[^{{]*\\{{",source)
    if not marker: return ""
    start=marker.end()-1; depth=0
    for i in range(start,len(source)):
        if source[i]=='{': depth+=1
        elif source[i]=='}':
            depth-=1
            if depth==0:return source[start+1:i]
    return ""
def generate_temporal_precondition_hypotheses(contract, semantic=()):
    public=[f for f in contract.functions if f.visibility in {"public","external"} and f.writes]
    inv=[]; hyps=[]
    for f in public:
        body=_body(contract,f)
        calls=[m.group(0) for m in re.finditer(r"\\b(?:call|_call|_execute|executeCall|externalCall)\\s*\\(",body)]
        if not calls: continue
        first_call=min((body.find(x) for x in calls if body.find(x)>=0),default=-1)
        checks=[m for m in re.finditer(r"\\b(?:require|assert)\\s*\\(([^;{}]+)",body) if m.start()>first_call and re.search(r"ready|valid|pending|done|timestamp|state|authorized|enabled",m.group(1),re.I)]
        if not checks: continue
        iid=f"INV-TEMPORAL-PRECONDITION-{f.name}"
        inv.append(Invariant(iid,"Security-relevant preconditions should be established before external state-changing calls when those calls can alter the predicate being checked.","call-order / precondition topology",0.72))
        hyps.append(Hypothesis(f"H-TEMPORAL-{f.name}",f"{f.name} may make an external state-changing call before checking a security-relevant precondition, allowing the call sequence to change the predicate and satisfy it retroactively.",iid,f.name,"authorized external caller able to reach the transition","a precondition that should constrain entry can become true during the transition",evidence_ids=(f"E-MODEL-{f.name}",)))
    return TemporalPreconditionContribution(tuple(inv),tuple(hyps))
