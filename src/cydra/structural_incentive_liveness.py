from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import re
from .models import ContractModel, Hypothesis, Invariant

@dataclass(frozen=True)
class IncentiveContribution:
    invariants: tuple[Invariant, ...]
    hypotheses: tuple[Hypothesis, ...]

def _body(contract, name):
    try: source=Path(contract.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError): return ""
    m=re.search(r"\bfunction\s+"+re.escape(name)+r"\s*\([^)]*\)[^{]*\{",source)
    if not m: return ""
    start=m.end()-1; depth=0
    for i in range(start,len(source)):
        if source[i]=="{": depth+=1
        elif source[i]=="}":
            depth-=1
            if depth==0: return source[start+1:i]
    return ""

def generate_incentive_liveness_hypotheses(contract: ContractModel, semantic=()):
    invariants=[]; hypotheses=[]; rewarders=[]; triggers=[]
    for f in contract.functions:
        if f.visibility not in {"public","external"}: continue
        body=_body(contract,f.name)
        if (re.search(r"(?:payable\s*\(\s*msg\.sender\s*\)|msg\.sender)\s*(?:\.\s*)?(?:transfer|send|call)",body) and re.search(r"(?:reward|fee|bounty|incentive|payout)",body,re.I)) or any(re.search(r"(?:keep|reward|incentive|bounty|payout|fee)", modifier, re.I) for modifier in f.modifiers):
            rewarders.append(f)
        if (re.search(r"(?:request|pending|queue|epoch|job|work)",f.name,re.I) and re.search(r"\+\+|\+=|push\s*\(",body)) or (re.search(r"\bfor\s*\(",body) and ".length" in body and any(re.search(r"(?:keep|reward|incentive|bounty|payout|fee)", modifier, re.I) for modifier in f.modifiers)):
            triggers.append(f)
    if not rewarders or not triggers: return IncentiveContribution((),())
    for rewarder in rewarders:
        iid="INV-INCENTIVE-LIVENESS-"+rewarder.name
        invariants.append(Invariant(iid,"A permissionless incentive payout must remain coupled to a value-bearing or bounded-cost state transition; a caller must not manufacture payout-eligible work at lower cost than the reward.","reward payout plus permissionless work/request topology",0.72))
        peers=tuple(t.name for t in triggers if t.name != rewarder.name)
        hypotheses.append(Hypothesis("H-INCENTIVE-LIVENESS-"+rewarder.name,rewarder.name+" may pay an incentive to a caller for work that a permissionless caller can manufacture without paying a commensurate cost.",iid,rewarder.name,"permissionless caller able to create payout-eligible work","attacker can increase payout-eligible work without value-bearing input and extract more reward than the cost of creating the work",evidence_ids=("E-MODEL-"+rewarder.name,),related_functions=peers))
    return IncentiveContribution(tuple(invariants),tuple(hypotheses))
