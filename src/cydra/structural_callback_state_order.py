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

# Calls through a value/contract expression are callback-capable. This deliberately
# includes ordinary interface/contract calls (for example helper.foo()) as well as
# low-level value transfers. Solidity builtins that cannot invoke target code are
# excluded so the surface remains a topology detector rather than a generic call
# counter.
_EXTERNAL_CALL_RE = re.compile(
    r"(?<![\w.])"
    r"(?:[A-Za-z_]\w*\s*\([^;{}]*\)|[A-Za-z_]\w*)"
    r"\s*\.\s*[A-Za-z_]\w*\s*\("
)
_NON_CALLBACK_RECEIVERS = {"abi", "block", "msg", "tx", "type", "super"}


def _source(contract: ContractModel) -> str:
    try:
        return Path(contract.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""


def _function_body(source: str, match: re.Match[str]) -> str:
    start = match.end() - 1
    depth = 0
    for index in range(start, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start + 1:index]
    return ""


def _external_callback_call(body: str) -> re.Match[str] | None:
    for match in _EXTERNAL_CALL_RE.finditer(body):
        receiver = match.group(0).split(".", 1)[0].strip()
        if receiver in _NON_CALLBACK_RECEIVERS:
            continue
        return match
    return None


def _external_value_transfer(body: str) -> bool:
    return bool(re.search(
        r"(?:\.call\s*\{\s*value\s*:|\.transfer\s*\(|\.send\s*\(|\.safeTransferETH\s*\()",
        body,
    ))


def _state_write_after_external_transfer(body: str) -> bool:
    transfer = re.search(
        r"(?:\.call\s*\{\s*value\s*:|\.transfer\s*\(|\.send\s*\(|\.safeTransferETH\s*\()",
        body,
    )
    if not transfer:
        return False
    tail = body[transfer.end():]
    return bool(re.search(
        r"\b[A-Za-z_]\w*(?:\s*\[[^\]]+\])*\s*(?:=|\+=|-=|\*=|/=|%=|\+\+|--)",
        tail,
    ))


def _state_write_after_external_call(body: str, call: re.Match[str]) -> bool:
    tail = body[call.end():]
    return bool(re.search(
        r"\b[A-Za-z_]\w*(?:\s*\[[^\]]+\])*\s*(?:=|\+=|-=|\*=|/=|%=|\+\+|--)",
        tail,
    ))


def _guarded(function) -> bool:
    return any(
        re.search(r"\b(?:nonReentrant|reentrancy|notInReentrant|notLocked)\b", modifier)
        for modifier in function.modifiers
    )


def _public_callers(function_name: str, functions) -> tuple:
    return tuple(
        function
        for function in functions
        if function.visibility in {"public", "external"}
        and re.search(rf"\b{re.escape(function_name)}\s*\(", _body_for_function(function))
    )


def _body_for_function(function) -> str:
    # This helper is replaced by the source-aware closure in the generator.
    return ""


def generate_callback_state_order_hypotheses(contract: ContractModel, semantic=()) -> CallbackStateOrderContribution:
    source = _source(contract)
    if not source:
        return CallbackStateOrderContribution((), ())

    parsed: list[tuple[object, str, str]] = []
    for match in _FUNCTION_RE.finditer(source):
        name = match.group("name")
        model = next((item for item in contract.functions if item.name == name), None)
        if model is not None:
            parsed.append((model, match.group("tail"), _function_body(source, match)))

    public_functions = {
        function.name: function
        for function, tail, _body in parsed
        if function.visibility in {"public", "external"}
    }

    invariants: list[Invariant] = []
    hypotheses: list[Hypothesis] = []
    seen: set[str] = set()

    for function, _tail, body in parsed:
        if not body:
            continue

        call = _external_callback_call(body)
        if call is None:
            continue

        # Preserve the original, narrower transfer surface exactly: value-transfer
        # callbacks remain candidates, but ordinary contract calls now get the same
        # conservative ordering analysis.
        has_ordering_gap = (
            _state_write_after_external_transfer(body)
            if _external_value_transfer(body)
            else _state_write_after_external_call(body, call)
        )
        if not has_ordering_gap:
            continue

        if function.visibility in {"public", "external"}:
            target_function = function
        else:
            callers = tuple(
                candidate
                for candidate in public_functions.values()
                if re.search(rf"\b{re.escape(function.name)}\s*\(", _body_for(candidate, source))
            )
            # A guarded public entry point cannot be used as the reentrant boundary
            # represented by this hypothesis. If several callers exist, retain an
            # unguarded one rather than manufacturing a candidate from a protected path.
            unguarded = tuple(candidate for candidate in callers if not _guarded(candidate))
            if not unguarded:
                continue
            target_function = unguarded[0]

        if _guarded(target_function):
            continue

        target = target_function.name
        hypothesis_id = f"H-CALLBACK-STATE-ORDER-{target}"
        if hypothesis_id in seen:
            continue
        seen.add(hypothesis_id)

        invariant_id = f"INV-CALLBACK-STATE-ORDER-{target}"
        invariants.append(Invariant(
            invariant_id,
            "Security-critical state establishing a temporal or authorization condition must be updated before an external contract call can invoke attacker-controlled code.",
            "external callback topology plus state-write ordering",
            0.80,
        ))
        hypotheses.append(Hypothesis(
            hypothesis_id,
            f"{target} may expose an intermediate state during an external contract call, allowing a reentrant caller to bypass a state-dependent condition before the condition is recorded.",
            invariant_id,
            target,
            "a caller-controlled contract able to receive an external callback and reenter the target",
            f"a reentrant call can exploit the pre-update state while {function.name} is still executing",
            evidence_ids=(f"E-MODEL-{target}",),
            related_functions=(function.name,) if function.name != target else (),
        ))

    return CallbackStateOrderContribution(tuple(invariants), tuple(hypotheses))


def _body_for(function, source: str) -> str:
    marker = re.search(
        rf"\bfunction\s+{re.escape(function.name)}\s*\([^)]*\)\s*[^\{{;]*\{{",
        source,
    )
    return _function_body(source, marker) if marker else ""
