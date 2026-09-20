from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .models import ContractModel, Hypothesis, Invariant


@dataclass(frozen=True)
class ReadOnlyReentrancyContribution:
    invariants: tuple[Invariant, ...]
    hypotheses: tuple[Hypothesis, ...]


def _body(contract: ContractModel, function) -> str:
    try:
        source = Path(contract.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""
    marker = re.search(
        rf"\bfunction\s+{re.escape(function.name)}\s*\([^)]*\)[^{{]*\{{",
        source,
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


def _view_functions(contract: ContractModel):
    return tuple(
        function
        for function in contract.functions
        if function.visibility in {"public", "external"}
        and "view" in _signature(contract, function)
    )


def _signature(contract: ContractModel, function) -> str:
    try:
        source = Path(contract.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""
    marker = re.search(
        rf"\bfunction\s+{re.escape(function.name)}\s*\([^)]*\)([^{{;]*)\{{",
        source,
    )
    return marker.group(1) if marker else ""


def _external_value_transfer(body: str) -> bool:
    return bool(
        re.search(
            r"(?:\.call\s*\{\s*value\s*:|\.transfer\s*\(|\.send\s*\(|\.safeTransfer\s*\()",
            body,
        )
    )


def _read_expression(body: str, variable: str) -> bool:
    return bool(re.search(rf"\b{re.escape(variable)}\b", body))


def _lock_guarded(contract: ContractModel, function) -> bool:
    signature = _signature(contract, function)
    body = _body(contract, function)
    return bool(
        re.search(r"\b(?:nonReentrant|reentrancy|notInReentrant|notLocked)\b", signature)
        or re.search(r"\b(?:locked|reentrancyLock|_locked)\b", body)
    )


def generate_read_only_reentrancy_hypotheses(
    contract: ContractModel, semantic=()
) -> ReadOnlyReentrancyContribution:
    invariants: list[Invariant] = []
    hypotheses: list[Hypothesis] = []

    state_changers = [
        function for function in contract.functions
        if function.visibility in {"public", "external"} and function.writes
    ]
    views = _view_functions(contract)

    for transition in state_changers:
        body = _body(contract, transition)
        if not body or not _external_value_transfer(body):
            continue
        if len(transition.writes) < 2:
            continue

        for view in views:
            view_body = _body(contract, view)
            shared = [name for name in transition.writes if _read_expression(view_body, name)]
            if len(shared) < 2:
                continue
            if _lock_guarded(contract, view):
                continue

            iid = f"INV-READONLY-REENTRANCY-{transition.name}-{view.name}"
            invariants.append(
                Invariant(
                    iid,
                    "A read-only observation used for a security or economic decision should not expose a state derived from an externally observable intermediate transition state.",
                    "cross-function state surface plus external-callback topology",
                    0.70,
                )
            )
            hypotheses.append(
                Hypothesis(
                    f"H-READONLY-{transition.name}-{view.name}",
                    f"{view.name} may observe an inconsistent intermediate state when called reentrantly during {transition.name}, allowing a consumer to use a transient value as if it represented settled state.",
                    iid,
                    transition.name,
                    "authorized caller able to receive an external value callback and invoke the public view during the transition",
                    f"{view.name} can return a materially different value before {transition.name} completes than it returns after settlement",
                    evidence_ids=(f"E-MODEL-{transition.name}", f"E-MODEL-{view.name}"),
                    related_functions=(view.name,),
                )
            )
            break

    return ReadOnlyReentrancyContribution(tuple(invariants), tuple(hypotheses))
