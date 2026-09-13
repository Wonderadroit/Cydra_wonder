from __future__ import annotations

import re
from pathlib import Path

from .models import ContractModel, Hypothesis


_FUNCTION_RE = re.compile(r"\bfunction\s+(?P<name>\w+)\s*\([^)]*\)\s*(?P<tail>[^\{;]*)\{", re.MULTILINE)
_INITIALIZER_MODIFIERS = {"initializer", "reinitializer"}
_VISIBILITIES = {"public", "external"}


def _declared_modifiers(contract: ContractModel, function) -> tuple[str, ...]:
    try:
        source = Path(contract.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ()
    for match in _FUNCTION_RE.finditer(source):
        if match.group("name") != function.name:
            continue
        line = source.count("\n", 0, match.start()) + 1
        if line != function.line:
            continue
        tail = re.sub(r"//[^\n]*|/\*.*?\*/", " ", match.group("tail"), flags=re.DOTALL)
        tokens = re.findall(r"\b[A-Za-z_]\w*\b", tail)
        modifiers: list[str] = []
        for token in tokens:
            if token in {"returns", "override", "virtual"}:
                break
            if token in {"public", "external", "internal", "private", "view", "pure", "payable"}:
                continue
            if token not in modifiers:
                modifiers.append(token)
        return tuple(modifiers)
    return ()


def generate_structural_initialization_hypotheses(contract: ContractModel) -> tuple[Hypothesis, ...]:
    """Discover lifecycle entry points from initializer semantics, not names."""
    hypotheses: list[Hypothesis] = []
    for function in contract.functions:
        if function.visibility not in _VISIBILITIES:
            continue
        modifiers = set(_declared_modifiers(contract, function))
        if not modifiers.intersection(_INITIALIZER_MODIFIERS):
            continue
        hypotheses.append(
            Hypothesis(
                f"H-INIT-{function.name}",
                f"{function.name} may be callable in a deployed uninitialized state by an arbitrary caller, allowing privileged initialization state to be claimed.",
                "INV-INIT-001",
                function.name,
                "arbitrary external caller",
                "attacker-controlled initialization or privileged state",
                evidence_ids=(f"E-MODEL-{function.name}",),
            )
        )
    return tuple(hypotheses)
