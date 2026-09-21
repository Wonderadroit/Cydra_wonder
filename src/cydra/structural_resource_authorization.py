from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .models import ContractModel, Hypothesis, Invariant


@dataclass(frozen=True)
class ResourceAuthorizationContribution:
    invariants: tuple[Invariant, ...]
    hypotheses: tuple[Hypothesis, ...]


_FUNCTION_RE = re.compile(
    r"\bfunction\s+(?P<name>\w+)\s*\((?P<params>[^)]*)\)\s*(?P<tail>[^\{;]*)\{",
    re.MULTILINE,
)
_TOKEN_ID_RE = re.compile(
    r"\b(?:uint(?:8|16|32|64|128|256)?|bytes32)\s+(?P<name>tokenId|positionId|resourceId)\b"
)
_AUTH_MODIFIERS = {"onlyOwner", "onlyAdmin", "onlyRole", "auth", "authorized"}


def _source(contract: ContractModel) -> str:
    try:
        return Path(contract.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""


def _function_body(source: str, match: re.Match[str]) -> str:
    start = match.end() - 1
    depth = 0
    for index in range(start, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start + 1:index]
    return ""


def generate_resource_authorization_hypotheses(contract: ContractModel, semantic=()) -> ResourceAuthorizationContribution:
    source = _source(contract)
    if not source:
        return ResourceAuthorizationContribution((), ())

    hypotheses: list[Hypothesis] = []
    for match in _FUNCTION_RE.finditer(source):
        tail = match.group("tail")
        if not any(token in tail.split() for token in ("public", "external")):
            continue
        modifiers = set(re.findall(r"\b[A-Za-z_]\w*\b", tail))
        if modifiers.intersection(_AUTH_MODIFIERS):
            continue

        token_match = _TOKEN_ID_RE.search(match.group("params"))
        if token_match is None:
            continue
        token_name = token_match.group("name")
        body = _function_body(source, match)
        if not body:
            continue

        # Generic resource-boundary evidence: the function resolves resource
        # state through the identifier and can mutate/withdraw that resource.
        resolves_resource = bool(
            re.search(
                rf"\b(?:positions|ownerOf|balanceOf|approve|collect|_collectFees|decreaseLiquidity|_decreaseLiquidity|increaseLiquidity|safeTransferFrom)\s*\([^)]*\b{re.escape(token_name)}\b",
                body,
                re.S,
            )
        )
        mutates_resource = bool(
            re.search(
                rf"\b(?:decreaseLiquidity|_decreaseLiquidity|increaseLiquidity|collect|_collectFees|safeTransferFrom|transferFrom|burn|withdraw)\s*\([^)]*\b{re.escape(token_name)}\b",
                body,
                re.S,
            )
        )
        if not (resolves_resource and mutates_resource):
            continue

        invariant_id = f"INV-RESOURCE-AUTH-{contract.name}"
        hypothesis_id = f"H-RESOURCE-AUTH-{match.group('name')}-{token_name}"
        invariant = Invariant(
            invariant_id,
            "An externally callable action over an owned resource must bind the caller to the resource owner or an explicitly delegated actor before mutating or withdrawing that resource.",
            "resource identifier, ownership boundary, and caller binding",
            0.90,
        )
        hypothesis = Hypothesis(
            hypothesis_id,
            f"{match.group('name')} may mutate or withdraw a resource identified by {token_name} without proving that msg.sender is authorized for that resource.",
            invariant_id,
            match.group("name"),
            "arbitrary external caller who can reach the resource-action entry point",
            "after a resource owner grants an approval or delegation, an unrelated caller can supply instructions for the same resource and cause a state or asset transition",
            evidence_ids=(f"E-MODEL-RESOURCE-{match.group('name')}", f"E-SOURCE-RESOURCE-{match.group('name')}"),
        )
        hypotheses.append(hypothesis)

    if not hypotheses:
        return ResourceAuthorizationContribution((), ())
    # Keep the surface class-neutral: one invariant represents the discovered
    # resource/caller boundary and each matching entry point is a competing
    # hypothesis under that invariant.
    invariant = hypotheses[0]
    return ResourceAuthorizationContribution(
        (Invariant(
            invariant.invariant_id,
            "An externally callable action over an owned resource must bind the caller to the resource owner or an explicitly delegated actor before mutating or withdrawing that resource.",
            "resource identifier, ownership boundary, and caller binding",
            0.90,
        ),),
        tuple(hypotheses),
    )
