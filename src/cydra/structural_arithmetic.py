from __future__ import annotations

import re
from pathlib import Path

from .models import ContractModel, Hypothesis, Invariant


_FUNCTION_RE = re.compile(
    r"\bfunction\s+(?P<name>\w+)\s*\([^)]*\)\s*(?P<tail>[^\{;]*)\{",
    re.MULTILINE,
)
_VISIBILITIES = {"public", "external"}


def _source(contract: ContractModel) -> str:
    try:
        return Path(contract.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""


def _body(source: str, match: re.Match[str]) -> str:
    start = match.end() - 1
    depth = 0
    for index in range(start, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start + 1:index]
    return ""


def _looks_like_upward_rounding(body: str) -> bool:
    """Detect positive-offset integer division without benchmark-specific names."""
    compact = re.sub(r"//[^\n]*|/\*.*?\*/", " ", body, flags=re.DOTALL)
    return bool(re.search(r"\([^(){};]*\+\s*[1-9]\d*\s*\)\s*/\s*[^/;,)]+", compact))


def arithmetic_rounding_invariant(contract: ContractModel) -> Invariant | None:
    source = _source(contract)
    if not source:
        return None
    function_names = {fn.name for fn in contract.functions}
    if not any(
        match.group("name") in function_names
        and _looks_like_upward_rounding(_body(source, match))
        for match in _FUNCTION_RE.finditer(source)
    ):
        return None
    return Invariant(
        "INV-ARITH-001",
        "Integer division must preserve the intended rounding direction; adding a positive offset before division may produce a value above the exact floor.",
        "structural arithmetic rule; positive-offset numerator followed by integer division",
        0.80,
    )


def generate_arithmetic_hypotheses(contract: ContractModel) -> tuple[Hypothesis, ...]:
    invariant = arithmetic_rounding_invariant(contract)
    if invariant is None:
        return ()
    source = _source(contract)
    functions = {fn.name: fn for fn in contract.functions if fn.visibility in _VISIBILITIES}
    hypotheses: list[Hypothesis] = []
    for match in _FUNCTION_RE.finditer(source):
        name = match.group("name")
        function = functions.get(name)
        if function is None or not _looks_like_upward_rounding(_body(source, match)):
            continue
        hypotheses.append(
            Hypothesis(
                f"H-ARITH-{name}",
                f"{name} may produce a value above the exact floor because a positive offset is added before integer division.",
                invariant.invariant_id,
                name,
                "boundary input that distinguishes exact floor from upward-rounded division",
                "observed output exceeds the exact floor by at least one unit",
                evidence_ids=(f"E-MODEL-{name}",),
            )
        )
    return tuple(hypotheses)
