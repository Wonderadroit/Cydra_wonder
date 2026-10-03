from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .models import ContractModel, Hypothesis, Invariant


@dataclass(frozen=True)
class CallbackStateOrderContribution:
    invariants: tuple[Invariant, ...]
    hypotheses: tuple[Hypothesis, ...]


_FUNCTION_RE = re.compile(
    r"\bfunction\s+(?P<name>\w+)\s*\((?P<params>[^)]*)\)\s*(?P<tail>[^\{;]*)\{",
    re.MULTILINE,
)

_EXTERNAL_INTERACTION_RE = re.compile(
    r"(?:"
    r"\.call\s*\{\s*value\s*:"
    r"|\.transfer\s*\("
    r"|\.send\s*\("
    r"|\.safeTransferETH\s*\("
    r"|\b[A-Za-z_]\w*\s*\.\s*[A-Za-z_]\w*\s*\("
    r")"
)


def _source(contract: ContractModel) -> str:
    try:
        return Path(contract.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""


def _function_body(source: str, match: re.Match[str]) -> str:
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


def _modeled_function_body(source: str, function_name: str) -> tuple[str, str]:
    """Recover a function body from the modeled name when signature parsing is too strict."""
    match = re.search(rf"\\bfunction\\s+{re.escape(function_name)}\\s*\\(", source)
    if match is None:
        return "", ""
    brace = source.find("{", match.end())
    if brace < 0:
        return "", ""
    depth = 0
    for index in range(brace, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[brace + 1:index], source[match.end():brace]
    return "", ""


def _external_interaction(body: str) -> re.Match[str] | None:
    return _EXTERNAL_INTERACTION_RE.search(body)


def _state_write_after_external_interaction(body: str, interaction: re.Match[str]) -> bool:
    tail = body[interaction.end():]
    return bool(re.search(
        r"\b[A-Za-z_]\w*(?:\s*\[[^\]]+\])*\s*(?:=|\+=|-=|\*=|/=|%=|\+\+|--)",
        tail,
    ))


def _public_callers(function_name: str, functions: tuple[tuple[str, str, str], ...]) -> tuple[str, ...]:
    return tuple(
        name
        for name, tail, body in functions
        if re.search(r"\b(?:public|external)\b", tail)
        and re.search(rf"\b{re.escape(function_name)}\s*\(", body)
    )


def _lock_guarded(tail: str, body: str) -> bool:
    """Return whether the callable is protected by a recognizable reentrancy guard."""
    return bool(
        re.search(r"\b(?:nonReentrant|reentrancyGuard|notInReentrant|notLocked)\b", tail)
        or re.search(r"\b(?:reentrancyLock|_reentrancyGuardEntered|_locked)\b", body)
    )


def _modeled_lock_guarded(contract: ContractModel, function_name: str) -> bool:
    """Use parsed function/modifier provenance when source-local regex is insufficient."""
    for function in (*contract.functions, *contract.inherited_functions):
        if function.name != function_name:
            continue
        if any(
            re.search(r"\b(?:nonReentrant|reentrancyGuard|notInReentrant|notLocked)\b", modifier)
            for modifier in function.modifiers
        ):
            return True
    return False


def _modeled_public_callers(contract: ContractModel, function_name: str) -> tuple[str, ...]:
    """Resolve public/external callers from the generic function model."""
    callers: list[str] = []
    for function in (*contract.functions, *contract.inherited_functions):
        if function.visibility not in {"public", "external"}:
            continue
        if function_name in function.internal_calls and function.name not in callers:
            callers.append(function.name)
    return tuple(callers)


def generate_callback_state_order_hypotheses(contract: ContractModel, semantic=()) -> CallbackStateOrderContribution:
    source = _source(contract)
    if not source:
        return CallbackStateOrderContribution((), ())

    parsed: list[tuple[str, str, str]] = []
    for match in _FUNCTION_RE.finditer(source):
        parsed.append((match.group("name"), match.group("tail"), _function_body(source, match)))

    public_names = {
        name for name, tail, _body in parsed
        if re.search(r"\b(?:public|external)\b", tail)
    }

    invariants: list[Invariant] = []
    hypotheses: list[Hypothesis] = []
    seen: set[str] = set()

    for function_name, tail, body in parsed:
        interaction = _external_interaction(body)
        if not body or interaction is None or not _state_write_after_external_interaction(body, interaction):
            continue

        if function_name in public_names:
            target = function_name
            target_entry = next((item for item in parsed if item[0] == target), None)
        else:
            callers = _public_callers(function_name, tuple(parsed))
            if not callers:
                callers = _modeled_public_callers(contract, function_name)
            if not callers:
                continue
            target = callers[0]
            target_entry = next((item for item in parsed if item[0] == target), None)

        # A reentrant call into the selected public wrapper is not a viable
        # experiment when that wrapper itself holds a recognizable reentrancy
        # lock for its entire execution.  Do not turn a syntactic
        # "external call followed by state write" into a false hypothesis.
        # Other public entry points can still be analyzed independently.
        if (
            (target_entry is not None and _lock_guarded(target_entry[1], target_entry[2]))
            or _modeled_lock_guarded(contract, target)
        ):
            continue

        hypothesis_id = f"H-CALLBACK-STATE-ORDER-{target}"
        if hypothesis_id in seen:
            continue
        seen.add(hypothesis_id)

        invariant_id = f"INV-CALLBACK-STATE-ORDER-{target}"
        invariants.append(Invariant(
            invariant_id,
            "Security-critical state establishing a temporal or authorization condition must be updated before an external interaction can invoke attacker-controlled code.",
            "external interaction topology plus state-write ordering",
            0.80,
        ))
        hypotheses.append(Hypothesis(
            hypothesis_id,
            f"{target} may expose an intermediate state during an external interaction, allowing a reentrant caller to bypass a state-dependent condition before the condition is recorded.",
            invariant_id,
            target,
            "a caller-controlled contract able to execute during an external interaction and reenter the target",
            f"a reentrant call can exploit the pre-update state while {function_name} is still executing",
            evidence_ids=(f"E-MODEL-{target}",),
            related_functions=(function_name,) if function_name != target else (),
        ))

    # Fallback to the canonical Solidity model when the permissive source
    # signature parser misses a declaration. This applies the same invariant
    # to the modeled function name; it is not target-specific knowledge.
    for modeled in (*contract.functions, *contract.inherited_functions):
        body, tail = _modeled_function_body(source, modeled.name)
        if not body:
            continue
        interaction = _external_interaction(body)
        if interaction is None or not _state_write_after_external_interaction(body, interaction):
            continue
        if modeled.visibility not in {"public", "external"}:
            callers = _modeled_public_callers(contract, modeled.name)
            if not callers:
                continue
            target = callers[0]
        else:
            target = modeled.name
        if _modeled_lock_guarded(contract, target) or _lock_guarded(tail, body):
            continue
        hypothesis_id = f"H-CALLBACK-STATE-ORDER-{target}"
        if hypothesis_id in seen:
            continue
        seen.add(hypothesis_id)
        invariant_id = f"INV-CALLBACK-STATE-ORDER-{target}"
        invariants.append(Invariant(
            invariant_id,
            "Security-critical state establishing a temporal or authorization condition must be updated before an external interaction can invoke attacker-controlled code.",
            "external interaction topology plus state-write ordering",
            0.80,
        ))
        hypotheses.append(Hypothesis(
            hypothesis_id,
            f"{target} may expose an intermediate state during an external interaction, allowing a reentrant caller to bypass a state-dependent condition before the condition is recorded.",
            invariant_id,
            target,
            "a caller-controlled contract able to execute during an external interaction and reenter the target",
            f"a reentrant call can exploit the pre-update state while {modeled.name} is still executing",
            evidence_ids=(f"E-MODEL-{target}",),
            related_functions=(modeled.name,) if modeled.name != target else (),
        ))

    return CallbackStateOrderContribution(tuple(invariants), tuple(hypotheses))
