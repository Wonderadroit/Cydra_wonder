from __future__ import annotations

import re
from pathlib import Path

from .models import ContractModel, Hypothesis, Invariant


_FUNCTION_RE = re.compile(
    r"\bfunction\s+(?P<name>\w+)\s*\((?P<parameters>[^)]*)\)\s*(?P<tail>[^\{;]*)\{",
    re.MULTILINE,
)
_WEIGHTED_AVERAGE_RE = re.compile(
    r"(?P<left>[^;{}]+?)\.div\s*\(\s*(?P<denominator>[^;{}]+?)\s*\)\s*;",
    re.DOTALL,
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
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start + 1:index]
    return ""


def _parameter_names(raw: str) -> tuple[str, ...]:
    names: list[str] = []
    for item in raw.split(","):
        tokens = re.findall(r"\b[A-Za-z_]\w*\b", item)
        if tokens:
            names.append(tokens[-1])
    return tuple(names)


def _is_weighted_average(body: str) -> bool:
    compact = re.sub(r"//[^\n]*|/\*.*?\*/", " ", body, flags=re.DOTALL)
    return bool(
        re.search(
            r"\.mul\s*\(\s*[A-Za-z_]\w*\s*\)\s*\.add\s*\([^;{}]+\.mul\s*\([^;{}]+\)\)\s*\.div\s*\(\s*[A-Za-z_]\w*\s*\.add\s*\([^)]*\)\s*\)",
            compact,
        )
    )


def weighted_average_rounding_invariant(contract: ContractModel) -> Invariant | None:
    source = _source(contract)
    if not source:
        return None
    for match in _FUNCTION_RE.finditer(source):
        params = _parameter_names(match.group("parameters"))
        if len(params) != 4 or not _is_weighted_average(_body(source, match)):
            continue
        if not all(
            any(p.name == name and p.type.startswith("uint") for p in next(
                (f for f in contract.functions if f.name == match.group("name") and f.line == source.count("\n", 0, match.start()) + 1),
                type("F", (), {"parameters": ()})(),
            ).parameters)
            for name in params
        ):
            continue
        return Invariant(
            "INV-ROUND-001",
            "A weighted average used for a conservative boundary must not round below the mathematical average when the exact result is fractional.",
            "structural weighted-average arithmetic; positive-weight numerator divided by the sum of weights",
            0.80,
        )
    return None


def generate_weighted_average_rounding_hypotheses(contract: ContractModel) -> tuple[Hypothesis, ...]:
    invariant = weighted_average_rounding_invariant(contract)
    if invariant is None:
        return ()
    source = _source(contract)
    hypotheses: list[Hypothesis] = []
    for match in _FUNCTION_RE.finditer(source):
        name = match.group("name")
        params = _parameter_names(match.group("parameters"))
        if len(params) != 4 or not _is_weighted_average(_body(source, match)):
            continue
        function = next((item for item in contract.functions if item.name == name), None)
        if function is None or not all(p.type.startswith("uint") for p in function.parameters):
            continue
        hypotheses.append(
            Hypothesis(
                f"H-ROUND-{name}",
                f"{name} may round a weighted average down when the exact result is fractional, weakening a conservative boundary invariant.",
                invariant.invariant_id,
                name,
                "caller-controlled positive weighted-average inputs",
                "observed result is below the mathematical ceiling of the weighted average",
                evidence_ids=(f"E-MODEL-{name}",),
            )
        )
    return tuple(hypotheses)
