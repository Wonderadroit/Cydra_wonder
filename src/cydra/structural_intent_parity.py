from __future__ import annotations

import re
from pathlib import Path

from .models import ContractModel, Hypothesis, Invariant


_FUNCTION_RE = re.compile(
    r"\bfunction\s+(?P<name>\w+)\s*\([^)]*\)\s*(?P<tail>[^\{;]*)\{",
    re.MULTILINE,
)
_CAMEL_RE = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\b)|\d+")
_ROLE_PAIR_RE = re.compile(
    r"\b([a-z][a-z0-9_]*)\b\s+(?:or|and)\s+(?:the\s+)?\b([a-z][a-z0-9_]*)\b",
    re.IGNORECASE,
)


def _preceding_comments(source: str, match_start: int) -> str:
    """Return the contiguous line-comment block immediately before a function."""
    line_start = source.rfind("\n", 0, match_start) + 1
    lines = []
    cursor = line_start
    while cursor > 0:
        previous_end = cursor - 1
        previous_start = source.rfind("\n", 0, previous_end) + 1
        line = source[previous_start:previous_end + 1].strip()
        if not line.startswith("//"):
            break
        lines.append(line.lstrip("/").strip())
        cursor = previous_start
    lines.reverse()
    return " ".join(lines)


def _identifier_tokens(identifier: str) -> set[str]:
    return {token.lower() for token in _CAMEL_RE.findall(identifier)}


def _documented_role_pairs(comment: str) -> tuple[tuple[str, str], ...]:
    return tuple(
        (left.lower(), right.lower())
        for left, right in _ROLE_PAIR_RE.findall(comment)
    )


def generate_intent_parity_hypotheses(
    contract: ContractModel, semantic=()
) -> tuple[Invariant, tuple[Hypothesis, ...]]:
    """Detect documented caller roles missing from an enforced modifier.

    This is deliberately class-neutral. It does not name a vulnerability class,
    target, modifier, or role vocabulary. It extracts role pairs from the
    function's own contiguous documentation and compares those role tokens with
    the tokens present in the enforced modifier names. The resulting mismatch
    is only a hypothesis; execution and causal verification decide whether it
    matters.
    """
    try:
        source = Path(contract.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return (), ()

    public = {f.name: f for f in contract.functions if f.visibility in {"public", "external"}}
    hypotheses = []
    invariants = []
    for match in _FUNCTION_RE.finditer(source):
        name = match.group("name")
        function = public.get(name)
        if function is None:
            continue

        comment = _preceding_comments(source, match.start()).lower()
        role_pairs = _documented_role_pairs(comment)
        if not role_pairs:
            continue

        modifier_tokens = set()
        for modifier in function.modifiers:
            modifier_tokens.update(_identifier_tokens(modifier))

        for left, right in role_pairs:
            documented_roles = (left, right)
            missing = tuple(role for role in documented_roles if role not in modifier_tokens)
            if not missing or not modifier_tokens:
                continue

            invariant_id = f"INV-INTENT-PARITY-{name}"
            invariants.append(Invariant(
                invariant_id,
                "A documented caller role boundary should not be narrower than the enforced caller boundary.",
                "source-linked role-intent versus modifier comparison",
                0.82,
            ))
            hypotheses.append(Hypothesis(
                f"H-INTENT-PARITY-{name}",
                f"{name} may enforce a narrower caller boundary than the documented role intent; documented role(s) {', '.join(missing)} are not represented by the observed modifier.",
                invariant_id,
                name,
                "a documented-but-excluded caller role",
                "a caller permitted by the documented role boundary is rejected by the enforced modifier",
                evidence_ids=(f"E-MODEL-{name}",),
            ))
            break

    return tuple(invariants), tuple(hypotheses)
