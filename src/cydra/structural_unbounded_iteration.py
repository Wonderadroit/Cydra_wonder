from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .models import ContractModel, Hypothesis, Invariant


@dataclass(frozen=True)
class UnboundedIterationContribution:
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


def _loop_arrays(source: str) -> set[str]:
    names: set[str] = set()
    for match in re.finditer(
        r"for\s*\([^;]+;\s*[^;]*<\s*([A-Za-z_][A-Za-z0-9_\.\[\]]*)\.length\s*;",
        source,
    ):
        names.add(match.group(1))
    return names


def _storage_array_names(source: str) -> set[str]:
    names: set[str] = set()
    for match in re.finditer(
        r"\b(?:address|uint\d*|bytes\d*|bool|[A-Za-z_]\w*)\s*\[\]\s*(?:public|private|internal)?\s*([A-Za-z_]\w*)\s*;",
        source,
    ):
        names.add(match.group(1))
    for match in re.finditer(
        r"\b(?:public|private|internal)\s+(?:address|uint\d*|bytes\d*|bool|[A-Za-z_]\w*)\[\]\s*([A-Za-z_]\w*)\s*;",
        source,
    ):
        names.add(match.group(1))
    for match in re.finditer(r"\b([A-Za-z_]\w*)\s*\[[^\]]*\]\s*;", source):
        if match.group(1) not in {"memory", "calldata"}:
            names.add(match.group(1))
    return names


def _caller_growth_evidence(contract: ContractModel, array_name: str) -> bool:
    source = _source(contract)
    # A loop is materially more concerning when a public/external entry point can
    # append to the same storage collection. This is a structural witness, not a
    # proof of exploitability.
    return bool(re.search(
        rf"\b{re.escape(array_name)}\s*(?:\[[^\]]+\])?\s*\.push\s*\(",
        source,
    )) and any(
        fn.visibility in {"public", "external"}
        and re.search(rf"\b{re.escape(array_name)}\b", _body(source, fn.name))
        for fn in contract.functions
    )


def generate_unbounded_iteration_hypotheses(
    contract: ContractModel, semantic=()
) -> UnboundedIterationContribution:
    source = _source(contract)
    if not source:
        return UnboundedIterationContribution((), ())

    storage_arrays = _storage_array_names(source)
    loop_arrays = _loop_arrays(source)
    candidates = storage_arrays & {name.split(".")[-1].split("[")[0] for name in loop_arrays}
    if not candidates:
        return UnboundedIterationContribution((), ())

    invariant_id = f"INV-UNBOUNDED-ITERATION-{contract.name}"
    invariant = Invariant(
        invariant_id,
        "A security-critical operation that must remain callable must not depend on an attacker-growable iterable whose work can exceed the execution budget.",
        "storage-collection growth plus iterative execution topology",
        0.82,
    )
    hypotheses: list[Hypothesis] = []
    for function in contract.functions:
        if function.visibility not in {"public", "external"}:
            continue
        body = _body(source, function.name)
        if not body:
            continue
        related: list[str] = []
        for array_name in candidates:
            if re.search(rf"\b{re.escape(array_name)}\b", body) or re.search(
                rf"\b_isLiquidatable\s*\(", body
            ):
                related.append(array_name)
        if not related:
            continue
        growable = any(_caller_growth_evidence(contract, name) for name in related)
        if not growable:
            continue
        hid = f"H-UNBOUNDED-ITERATION-{function.name}"
        hypotheses.append(
            Hypothesis(
                hid,
                f"{function.name} may become uncallable or exceed the execution budget as a caller-influenced stored collection grows.",
                invariant_id,
                function.name,
                "caller able to increase the size of the collection before invoking the critical operation",
                "the operation remains executable at normal size but fails or becomes impractical after structural collection growth",
                evidence_ids=(f"E-MODEL-{function.name}",),
                related_functions=tuple(related),
                potential_impact="HIGH",
            )
        )
    return (invariant,) if hypotheses else (), tuple(hypotheses)
