from __future__ import annotations

import re
from pathlib import Path

from .models import ContractModel, Hypothesis


_FUNCTION_RE = re.compile(r"\bfunction\s+(?P<name>\w+)\s*\([^)]*\)\s*(?P<tail>[^\{;]*)\{", re.MULTILINE)
_INITIALIZER_MODIFIERS = {"initializer", "reinitializer"}
_VISIBILITIES = {"public", "external"}
_LIFECYCLE_NAMES = {"initialize", "initialise", "init"}


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
        lifecycle_named = function.name.lower() in _LIFECYCLE_NAMES
        modifier_marked = bool(modifiers.intersection(_INITIALIZER_MODIFIERS))
        if not (modifier_marked or lifecycle_named):
            continue
        evidence_id = f"E-MODEL-{function.name}"
        if lifecycle_named and not modifier_marked:
            evidence_id = f"E-LIFECYCLE-NAME-{function.name}"
        hypotheses.append(
            Hypothesis(
                f"H-INIT-{function.name}",
                f"{function.name} may be callable in a deployed uninitialized state by an arbitrary caller, allowing privileged initialization state to be claimed.",
                "INV-INIT-001",
                function.name,
                "arbitrary external caller",
                "attacker-controlled initialization or privileged state",
                evidence_ids=(evidence_id,),
            )
        )
    return tuple(hypotheses)
