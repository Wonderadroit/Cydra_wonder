from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .models import ContractModel, FunctionModel, Hypothesis, Invariant


@dataclass(frozen=True)
class StoragePersistenceContribution:
    invariants: tuple[Invariant, ...]
    hypotheses: tuple[Hypothesis, ...]


def _body(contract: ContractModel, function: FunctionModel) -> str:
    try:
        source = Path(contract.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""
    marker = re.search(
        rf"\bfunction\s+{re.escape(function.name)}\s*\([^)]*\)[^{]*\{{",
        source,
    )
    if not marker:
        return ""
    start = marker.end() - 1
    depth = 0
    for i in range(start, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start + 1:i]
    return ""


def _storage_alias_mutated(contract: ContractModel, function: FunctionModel) -> bool:
    body = _body(contract, function)
    return bool(
        re.search(r"\b[A-Za-z_]\w*\s*=\s*[A-Za-z_]\w*\s*\[[^\]]+\]", body)
        and re.search(r"\b[A-Za-z_]\w*\s*\.\s*[A-Za-z_]\w+\s*=", body)
    )


def _memory_return(contract: ContractModel, function: FunctionModel) -> bool:
    try:
        source = Path(contract.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return False
    marker = re.search(
        rf"\bfunction\s+{re.escape(function.name)}\s*\([^)]*\)[^{]*\{{",
        source,
    )
    if not marker:
        return False
    header = source[source.rfind("function", 0, marker.end()):marker.end()]
    return bool(re.search(r"\breturns\s*\([^)]*\bmemory\b[^)]*\)", header))


def _caller_reaches_internal(contract: ContractModel, public_fn: FunctionModel, internal_fn: FunctionModel) -> bool:
    body = _body(contract, public_fn)
    return bool(re.search(rf"\b{re.escape(internal_fn.name)}\s*\(", body))


def generate_storage_persistence_hypotheses(
    contract: ContractModel, semantic=()
) -> StoragePersistenceContribution:
    """Find externally reachable state transitions that mutate a memory copy."""
    invariants: list[Invariant] = []
    hypotheses: list[Hypothesis] = []

    internal = [
        f for f in contract.functions
        if f.visibility in {"internal", "private"} and _storage_alias_mutated(contract, f)
    ]
    for helper in internal:
        if not _memory_return(contract, helper):
            continue
        callers = [
            f for f in contract.functions
            if f.visibility in {"public", "external"}
            and _caller_reaches_internal(contract, f, helper)
        ]
        for caller in callers:
            iid = f"INV-STORAGE-PERSISTENCE-{caller.name}"
            invariants.append(
                Invariant(
                    iid,
                    "A successful state-changing operation must persist the modeled state transition across the transaction boundary.",
                    "storage-reference / persistence topology",
                    0.79,
                )
            )
            hypotheses.append(
                Hypothesis(
                    f"H-STORAGE-PERSISTENCE-{caller.name}",
                    f"{caller.name} may report a successful state transition without persisting the mutated storage element because a downstream helper mutates a memory alias.",
                    iid,
                    caller.name,
                    "authorized caller able to invoke the public state-changing operation",
                    "the operation appears successful but the intended persistent state remains unchanged",
                    evidence_ids=(f"E-MODEL-{caller.name}",),
                    related_functions=(helper.name,),
                )
            )
    return StoragePersistenceContribution(tuple(invariants), tuple(hypotheses))
