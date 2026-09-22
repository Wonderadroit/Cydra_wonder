from __future__ import annotations

import re
from pathlib import Path

from .models import ContractModel, Hypothesis, Invariant


_FUNCTION_RE = re.compile(
    r"\bfunction\s+(?P<name>\w+)\s*\([^)]*\)\s*(?P<tail>[^\{;]*)\{",
    re.MULTILINE,
)


def _source(contract: ContractModel) -> str:
    try:
        return Path(contract.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""


def _body(source: str, match: re.Match[str]) -> str:
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


def _has_clamp_then_late_balance(body: str) -> bool:
    """Detect aggregation that clamps per-loop contributions before a later balance addition.

    This is a structural accounting smell, not a finding. The detector deliberately
    reasons from accumulator topology rather than target-specific names.
    """
    compact = re.sub(r"//[^\n]*|/\*.*?\*/", " ", body, flags=re.DOTALL)

    clamp = re.search(
        r"(?P<acc>[A-Za-z_]\w*)\s*\+=\s*uint256\s*\(\s*"
        r"Math\.max\s*\(\s*[^;{}]*?,\s*0\s*\)\s*\)\s*;",
        compact,
    )
    if not clamp:
        return False

    accumulator = clamp.group("acc")
    prefix = compact[: clamp.start()]
    suffix = compact[clamp.end() :]

    # The clamp must occur inside an iteration construct. This avoids flagging
    # ordinary final aggregation that happens only once.
    loop_open = max(prefix.rfind("for ("), prefix.rfind("while ("))
    if loop_open < 0:
        return False

    later_balance = re.search(
        rf"if\s*\(\s*!\s*(?P<skip>[A-Za-z_]\w*)\s*\)\s*"
        rf"\{{?\s*{re.escape(accumulator)}\s*\+=\s*"
        rf"[^;]*\.balanceOf\s*\(",
        suffix,
    )
    return later_balance is not None


def aggregation_order_invariant(contract: ContractModel) -> Invariant | None:
    source = _source(contract)
    if not source:
        return None

    functions = {
        fn.name
        for fn in contract.functions
        if fn.visibility in {"public", "external"}
    }
    if not any(
        match.group("name") in functions
        and _has_clamp_then_late_balance(_body(source, match))
        for match in _FUNCTION_RE.finditer(source)
    ):
        return None

    return Invariant(
        "INV-AGGREGATION-ORDER-001",
        "Equivalent economic components must be aggregated before a non-linear clamp; applying the clamp to partial totals can make the result depend on configuration or grouping.",
        "structural accounting rule; per-iteration clamp followed by deferred balance addition",
        0.80,
    )


def generate_aggregation_order_hypotheses(contract: ContractModel) -> tuple[Hypothesis, ...]:
    invariant = aggregation_order_invariant(contract)
    if invariant is None:
        return ()

    source = _source(contract)
    functions = {
        fn.name: fn
        for fn in contract.functions
        if fn.visibility in {"public", "external"}
    }
    hypotheses: list[Hypothesis] = []

    for match in _FUNCTION_RE.finditer(source):
        name = match.group("name")
        function = functions.get(name)
        if function is None or not _has_clamp_then_late_balance(_body(source, match)):
            continue

        hypotheses.append(
            Hypothesis(
                f"H-AGGREGATION-ORDER-{name}",
                f"{name} may apply a non-linear clamp to partial economic totals before adding a later balance, making an equivalent state depend on how components are grouped or configured.",
                invariant.invariant_id,
                name,
                "construct equivalent component values under two valid grouping or configuration arrangements",
                "equivalent economic states produce materially different aggregate values",
                evidence_ids=(f"E-MODEL-{name}",),
            )
        )

    return tuple(hypotheses)
