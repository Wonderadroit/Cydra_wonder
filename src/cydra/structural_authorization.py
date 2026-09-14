from __future__ import annotations

import re
from pathlib import Path

from .models import ContractModel, Hypothesis


_FUNCTION_RE = re.compile(r"\bfunction\s+(?P<name>\w+)\s*\([^)]*\)\s*(?P<tail>[^\{;]*)\{", re.MULTILINE)
_VISIBILITIES = {"public", "external"}
_CALLER_TOKEN_RE = re.compile(r"\b(?:msg\.sender|_msgSender\(\)|tx\.origin)\b")
_CALLER_KEYED_READ_RE = re.compile(r"\b[A-Za-z_]\w*\s*\[[^\]]*\b(?:msg\.sender|_msgSender\(\)|tx\.origin)\b[^\]]*\](?:\s*\[[^\]]*\])*")
_STATE_WRITE_RE = re.compile(r"\b(?P<name>[A-Za-z_]\w*)\s*(?:\[[^\]]*\])*\s*(?P<op>=|\+=|-=|\*=|/=|%=|\+\+|--)")


def _source_function_body(contract: ContractModel, function) -> str:
    try:
        source = Path(contract.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""
    for match in _FUNCTION_RE.finditer(source):
        if match.group("name") != function.name or source.count("\n", 0, match.start()) + 1 != function.line:
            continue
        depth = 1
        body_start = match.end()
        for index in range(body_start, len(source)):
            if source[index] == "{":
                depth += 1
            elif source[index] == "}":
                depth -= 1
                if depth == 0:
                    return source[body_start:index]
        return source[body_start:]
    return ""


def _source_state_writes(contract: ContractModel, function) -> tuple[str, ...]:
    """Return explicit state-root mutations visible in this function body.

    This is intentionally conservative. A model-level ``writes`` entry is not
    enough to establish a mutation because reads/getters can be represented as
    state-related expressions. Only direct assignment or increment/decrement
    syntax is accepted here; internal-call side effects remain a future
    data-flow milestone rather than being guessed.
    """
    body = _source_function_body(contract, function)
    if not body:
        return ()
    state_names = set(contract.state_variables)
    if not state_names:
        return ()
    writes: list[str] = []
    for match in _STATE_WRITE_RE.finditer(body):
        name = match.group("name")
        if name in state_names and name not in writes:
            writes.append(name)
    return tuple(writes)


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
        source_writes = _source_state_writes(contract, function)
        if function.visibility not in _VISIBILITIES or not source_writes:
            continue
        if _declared_modifiers(contract, function) or _has_caller_authorization_predicate(function):
            continue
        if not protected.intersection(source_writes):
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
