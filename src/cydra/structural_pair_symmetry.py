from __future__ import annotations

import re
from pathlib import Path

from .models import ContractModel, Hypothesis, Invariant


_FUNCTION_RE = re.compile(
    r"\bfunction\s+(?P<name>\w+)\s*\([^)]*\)\s*(?P<tail>[^\{;]*)\{",
    re.MULTILINE,
)
_ASSIGNMENT_RE = re.compile(
    r"(?P<lhs>\w+(?P<channel>[01]))\s*=\s*(?P<left>[^;=]+?)\s*-\s*(?P<right>[^;=]+?)\s*;",
    re.DOTALL,
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


def _operand_key(value: str) -> str:
    compact = re.sub(r"\s+", "", value)
    compact = re.sub(r"\.(?:leftSlot|rightSlot)\(\)", ".SLOT()", compact)
    compact = re.sub(r"\b(?:int\d*|uint\d*)\(", "TYPE(", compact)
    return compact


def paired_subtraction_invariant(contract: ContractModel) -> Invariant | None:
    source = _source(contract)
    if not source:
        return None

    function_names = {fn.name for fn in contract.functions}
    for match in _FUNCTION_RE.finditer(source):
        if match.group("name") not in function_names:
            continue
        body = _body(source, match)
        assignments = {}
        for assignment in _ASSIGNMENT_RE.finditer(body):
            base = assignment.group("lhs")[:-1]
            channel = assignment.group("channel")
            assignments.setdefault(base, {})[channel] = (
                _operand_key(assignment.group("left")),
                _operand_key(assignment.group("right")),
            )
        for channels in assignments.values():
            if "0" in channels and "1" in channels:
                left0, right0 = channels["0"]
                left1, right1 = channels["1"]
                if left0 == right1 and right0 == left1 and left0 != right0:
                    return Invariant(
                        "INV-PAIR-SYMMETRY-001",
                        "Paired channel calculations should preserve operand ordering unless a source-grounded invariant justifies reversing the operands.",
                        "structural paired-output subtraction symmetry",
                        0.65,
                    )
    return None


def generate_pair_symmetry_hypotheses(contract: ContractModel, _semantic=()) -> tuple[Hypothesis, ...]:
    invariant = paired_subtraction_invariant(contract)
    if invariant is None:
        return ()

    source = _source(contract)
    functions = {
        fn.name: fn for fn in contract.functions if fn.visibility in _VISIBILITIES
    }
    hypotheses: list[Hypothesis] = []

    for match in _FUNCTION_RE.finditer(source):
        name = match.group("name")
        function = functions.get(name)
        if function is None:
            continue

        body = _body(source, match)
        assignments = {}
        for assignment in _ASSIGNMENT_RE.finditer(body):
            base = assignment.group("lhs")[:-1]
            channel = assignment.group("channel")
            assignments.setdefault(base, {})[channel] = (
                _operand_key(assignment.group("left")),
                _operand_key(assignment.group("right")),
            )

        for base, channels in assignments.items():
            if "0" not in channels or "1" not in channels:
                continue
            left0, right0 = channels["0"]
            left1, right1 = channels["1"]
            if left0 != right1 or right0 != left1 or left0 == right0:
                continue

            hypotheses.append(
                Hypothesis(
                    f"H-PAIR-SYMMETRY-{name}-{base}",
                    f"{name} computes paired outputs {base}0 and {base}1 from the same two quantities but reverses their subtraction order; the asymmetry may invert the contribution of one channel.",
                    invariant.invariant_id,
                    name,
                    "execute the paired computation with deliberately asymmetric operand values",
                    "the paired output differs from the source-grounded same-order reference by a material signed contribution",
                    evidence_ids=(f"E-MODEL-{name}",),
                )
            )
    return tuple(hypotheses)
