from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import re
from .models import ContractModel, Hypothesis, Invariant

@dataclass(frozen=True)
class SignatureReplayContribution:
    invariants: tuple[Invariant, ...]
    hypotheses: tuple[Hypothesis, ...]

def _source(c: ContractModel) -> str:
    try:
        return Path(c.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""

def _body(source: str, name: str) -> str:
    m = re.search(rf"\bfunction\s+{re.escape(name)}\s*\([^)]*\)[^{{]*\{{", source, re.S)
    if not m:
        return ""
    start, depth = m.end() - 1, 0
    for i in range(start, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start + 1:i]
    return ""

def generate_signature_replay_hypotheses(contract: ContractModel, semantic=()):
    source = _source(contract)
    invariants, hypotheses = [], []
    for f in contract.functions:
        if f.visibility not in {"public", "external"}:
            continue
        body = _body(source, f.name)
        if not body or not re.search(r"signature|sig", body, re.I):
            continue
        if not re.search(r"validateAndSaveSignature|verifySignature|recover\s*\(", body, re.I):
            continue
        digest_call = re.search(r"(?:keccak256|_hashTypedDataV4)\s*\([^;]+\)", body, re.S)
        if not digest_call:
            continue
        digest = digest_call.group(0)
        if re.search(r"block\.chainid|chainid|address\s*\(\s*this\s*\)", digest, re.I):
            continue
        iid = f"INV-SIGNATURE-REPLAY-{f.name}"
        invariants.append(Invariant(iid, "A signed authorization must be bound to the intended execution domain so a valid signature cannot authorize the same action in another deployment or chain.", "signature authorization / domain separation topology", 0.82))
        hypotheses.append(Hypothesis(f"H-SIGNATURE-REPLAY-{f.name}", f"{f.name} may accept a valid signature outside its intended execution domain because the signed message is not observed to bind chain or contract context.", iid, f.name, "attacker who obtains a valid authorized signature", "the same signed authorization is accepted by another deployment or chain with equivalent signer and message inputs", evidence_ids=(f"E-MODEL-{f.name}",)))
    return SignatureReplayContribution(tuple(invariants), tuple(hypotheses))
