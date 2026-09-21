from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .models import ContractModel, Hypothesis, Invariant


@dataclass(frozen=True)
class SignedMetadataContribution:
    invariants: tuple[Invariant, ...]
    hypotheses: tuple[Hypothesis, ...]


def _source(contract: ContractModel) -> str:
    try:
        return Path(contract.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""


def _body(source: str, name: str) -> str:
    marker = re.search(
        rf"\bfunction\s+{re.escape(name)}\s*\([^)]*\)[^{{;]*\{{",
        source,
        re.S,
    )
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


def generate_signed_metadata_hypotheses(
    contract: ContractModel, semantic=()
) -> SignedMetadataContribution:
    """Detect authorization metadata parsed from a signature but not bound to its digest."""
    source = _source(contract)
    invariants: list[Invariant] = []
    hypotheses: list[Hypothesis] = []

    for function in contract.functions:
        body = _body(source, function.name)
        if not body:
            continue
        if not re.search(r"\b(?:signature|sig)\b", body, re.I):
            continue
        if not re.search(r"\b(?:recover|ecrecover|ECDSA\.[A-Za-z_]*)\s*\(", body, re.I):
            continue

        metadata_names = tuple(dict.fromkeys(re.findall(
            r"\b(?:validUntil|validAfter|deadline|expiry|nonce|domain|chainId|validFrom|notBefore)\b",
            body,
            re.I,
        )))
        if not metadata_names:
            continue

        base_hash_match = re.search(
            r"\b(?:hash|digest|signedHash)\b\s*=\s*[^;\n]*(?:userOpHash|messageHash|payloadHash|structHash|authorizationHash)[^;\n]*;",
            body,
            re.I,
        )
        if not base_hash_match:
            continue

        digest_region = body[:base_hash_match.end()]
        if any(re.search(rf"\b{re.escape(name)}\b", digest_region, re.I) for name in metadata_names):
            continue

        iid = f"INV-SIGNED-METADATA-{function.name}"
        hid = f"H-SIGNED-METADATA-{function.name}"
        invariants.append(Invariant(
            iid,
            "Authorization metadata that changes signature validity must be cryptographically bound to the signed message.",
            "signed-message integrity / auxiliary authorization metadata binding",
            0.91,
        ))
        hypotheses.append(Hypothesis(
            hid,
            f"{function.name} may accept authorization metadata that was not authenticated by the signer because the recovered digest is derived from a base authorization hash without the observed validity metadata.",
            iid,
            function.name,
            "a caller or relayer who can preserve a valid signature while changing the unauthenticated metadata",
            "the authorization can remain valid outside the signer's intended metadata constraints",
            evidence_ids=(
                f"E-MODEL-SIGNED-METADATA-{function.name}",
                f"E-DIGEST-BASE-ONLY-{function.name}",
            ),
        ))

    return SignedMetadataContribution(tuple(invariants), tuple(hypotheses))
