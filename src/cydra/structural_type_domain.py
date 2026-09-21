from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .models import ContractModel, Hypothesis, Invariant

@dataclass(frozen=True)
class TypeDomainContribution:
    invariants: tuple[Invariant, ...]
    hypotheses: tuple[Hypothesis, ...]

def _source(contract: ContractModel) -> str:
    try:
        return Path(contract.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""

def _body(source: str, name: str) -> str:
    marker = re.search(rf"\bfunction\s+{re.escape(name)}\s*\([^)]*\)[^{{;]*\{{", source, re.S)
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

def _mapping_widths(source: str) -> dict[str, str]:
    return {name: width for width, name in re.findall(
        r"mapping\s*\(\s*uint(8|16|32|64|128|256)\s*=>[^)]*\)\s+\w+\s+public\s+(\w+)", source
    )}

def generate_type_domain_hypotheses(contract: ContractModel, semantic=()) -> TypeDomainContribution:
    source = _source(contract)
    if not source:
        return TypeDomainContribution((), ())
    mapping_widths = _mapping_widths(source)
    if not mapping_widths:
        return TypeDomainContribution((), ())
    invariant_id = f"INV-TYPE-DOMAIN-{contract.name}"
    invariant = Invariant(
        invariant_id,
        "An externally supplied identifier must preserve the domain required by the state or protocol identifier it indexes; a narrower ABI type must not silently make valid identifiers unreachable.",
        "parameter-domain versus referenced-state-width comparison",
        0.90,
    )
    hypotheses = []
    for function in contract.functions:
        if function.visibility not in {"public", "external"}:
            continue
        body = _body(source, function.name)
        for parameter in function.parameters:
            if parameter.type not in {"uint8", "uint16", "uint32", "uint64", "uint128"} or parameter.name not in body:
                continue
            indexed = any(
                width == "256" and re.search(
                    rf"\b{re.escape(mapping_name)}\s*\[[^\]]*\b{re.escape(parameter.name)}\b", body
                )
                for mapping_name, width in mapping_widths.items()
            )
            if not indexed:
                continue
            hid = f"H-TYPE-DOMAIN-{function.name}-{parameter.name}"
            hypotheses.append(Hypothesis(
                hid,
                f"{function.name} may narrow the valid domain of {parameter.name} before indexing a wider identifier/state domain, making otherwise valid high-range identifiers unreachable.",
                invariant_id,
                function.name,
                "caller able to supply an identifier at or above the declared integer width boundary",
                "a boundary identifier accepted by the underlying state/protocol domain cannot reach the function through its declared ABI type, while the widened control accepts it",
                evidence_ids=(f"E-MODEL-{function.name}",),
            ))
            break
    return TypeDomainContribution((invariant,) if hypotheses else (), tuple(hypotheses))
