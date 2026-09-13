from __future__ import annotations

import re
from pathlib import Path

from .models import ContractModel, Hypothesis


_FUNCTION_RE = re.compile(r"\bfunction\s+(?P<name>\w+)\s*\([^)]*\)\s*(?P<tail>[^\{;]*)\{", re.MULTILINE)
_VISIBILITIES = {"public", "external"}
_CALLER_TOKEN_RE = re.compile(r"\b(?:msg\.sender|_msgSender\(\)|tx\.origin)\b")
_CALLER_KEYED_READ_RE = re.compile(r"\b[A-Za-z_]\w*\s*\[[^\]]*\b(?:msg\.sender|_msgSender\(\)|tx\.origin)\b[^\]]*\](?:\s*\[[^\]]*\])*")


def _declared_modifiers(contract: ContractModel, function) -> tuple[str, ...]:
    try:
        source = Path(contract.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ()
    for match in _FUNCTION_RE.finditer(source):
        if match.group("name") != function.name or source.count("\n", 0, match.start()) + 1 != function.line:
            continue
        tail = re.sub(r"//[^\n]*|/\*.*?\*/", " ", match.group("tail"), flags=re.DOTALL)
        tokens = re.findall(r"\b[A-Za-z_]\w*\b", tail)
        modifiers: list[str] = []
        for token in tokens:
            if token in {"returns", "override", "virtual"}:
                break
            if token not in {"public", "external", "internal", "private", "view", "pure", "payable"} and token not in modifiers:
                modifiers.append(token)
        return tuple(modifiers)
    return ()


def _has_caller_authorization_predicate(function) -> bool:
    for predicate in function.authorization_predicates:
        residual = _CALLER_KEYED_READ_RE.sub(" ", predicate)
        if _CALLER_TOKEN_RE.search(residual):
            return True
    return False


def generate_structural_access_control_hypotheses(contract: ContractModel) -> tuple[Hypothesis, ...]:
    """Find unguarded writers to storage also written by protected siblings."""
    protected = {
        write
        for function in contract.functions
        if function.visibility in _VISIBILITIES and _declared_modifiers(contract, function)
        for write in function.writes
    }
    if not protected:
        return ()

    hypotheses: list[Hypothesis] = []
    for function in contract.functions:
        if function.visibility not in _VISIBILITIES or not function.writes:
            continue
        if _declared_modifiers(contract, function) or _has_caller_authorization_predicate(function):
            continue
        if not protected.intersection(function.writes):
            continue
        hypotheses.append(
            Hypothesis(
                f"H-AUTH-{function.name}",
                f"{function.name} may permit an unauthorized caller to mutate state also controlled by a protected sibling.",
                "INV-AUTH-001",
                function.name,
                "arbitrary external caller",
                "state shared with a protected administrative path can be changed without its authorization mechanism",
                evidence_ids=(f"E-MODEL-{function.name}",),
            )
        )
    return tuple(hypotheses)
