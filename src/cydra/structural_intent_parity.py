from __future__ import annotations

import re
from pathlib import Path

from .models import ContractModel, Hypothesis, Invariant


_FUNCTION_RE = re.compile(
    r"\bfunction\s+(?P<name>\w+)\s*\([^)]*\)\s*(?P<tail>[^\{;]*)\{",
    re.MULTILINE,
)


def generate_intent_parity_hypotheses(
    contract: ContractModel, semantic=()
) -> tuple[Invariant, tuple[Hypothesis, ...]]:
    """Detect documented role boundaries that are narrower than enforcement.

    The detector treats comments as intent evidence only. It does not infer that
    the comment is correct; it creates a hypothesis that must be executed and
    causally verified.
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
        line_start = source.rfind("\n", 0, match.start()) + 1
        prefix = source[max(0, source.rfind("\n", 0, line_start - 1) + 1):line_start]
        comment = prefix.lower()
        tail = match.group("tail")
        modifiers = re.findall(r"\b[A-Za-z_]\w*\b", tail)
        if "onlyExecutor" not in modifiers:
            continue
        if not re.search(r"owner\s+or\s+(?:the\s+)?(?:avm|executor)", comment):
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
            f"{name} may enforce a narrower caller boundary than the documented role intent.",
            invariant_id,
            name,
            "a documented-but-excluded caller role",
            "a caller permitted by the documented role boundary is rejected by the enforced modifier",
            evidence_ids=(f"E-MODEL-{name}",),
        ))
    return tuple(invariants), tuple(hypotheses)
