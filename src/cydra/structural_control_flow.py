from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .models import ContractModel, Hypothesis, Invariant


@dataclass(frozen=True)
class ControlFlowContribution:
    invariants: tuple[Invariant, ...]
    hypotheses: tuple[Hypothesis, ...]


def _source(contract: ContractModel) -> str:
    try:
        return Path(contract.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""


def _functions(source: str) -> tuple[tuple[str, str, str], ...]:
    found: list[tuple[str, str, str]] = []
    for match in re.finditer(
        r"\bfunction\s+(?P<name>[A-Za-z_]\w*)\s*\([^)]*\)\s*"
        r"(?P<tail>[^\{;]*)\{",
        source,
        re.S,
    ):
        visibility_match = re.search(r"\b(public|external)\b", match.group("tail"))
        if not visibility_match:
            continue
        opening = match.end() - 1
        depth = 0
        end = None
        for index in range(opening, len(source)):
            if source[index] == "{":
                depth += 1
            elif source[index] == "}":
                depth -= 1
                if depth == 0:
                    end = index
                    break
        if end is not None:
            found.append((match.group("name"), visibility_match.group(1), source[opening + 1:end]))
    return tuple(found)


def _balanced_block(text: str, opening: int) -> str:
    depth = 0
    for index in range(opening, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[opening + 1:index]
    return ""


def _progress_bypassed(body: str) -> bool:
    for_match = re.search(
        r"for\s*\(\s*(?:uint\d*\s+)?(?P<counter>[A-Za-z_]\w*)\s*=\s*[^;]+;\s*[^;]+;\s*\)\s*\{",
        body,
        re.S,
    )
    if not for_match:
        return False

    counter = for_match.group("counter")
    loop_body = _balanced_block(body, for_match.end() - 1)
    if not loop_body or "continue" not in loop_body:
        return False

    increment = re.compile(
        rf"\b(?:{re.escape(counter)}\+\+|\+\+{re.escape(counter)}|{re.escape(counter)}\s*\+=\s*1)\b"
    )
    continue_positions = [m.start() for m in re.finditer(r"\bcontinue\s*;", loop_body)]
    if not continue_positions:
        return False

    for position in continue_positions:
        if increment.search(loop_body[:position]):
            return False

    return bool(increment.search(loop_body))


def generate_control_flow_hypotheses(contract: ContractModel, semantic=()) -> ControlFlowContribution:
    source = _source(contract)
    if not source:
        return ControlFlowContribution((), ())

    invariants: list[Invariant] = []
    hypotheses: list[Hypothesis] = []

    for function_name, visibility, body in _functions(source):
        if visibility not in {"public", "external"} or not _progress_bypassed(body):
            continue

        iid = f"INV-CONTROL-FLOW-{function_name}"
        hid = f"H-CONTROL-FLOW-{function_name}"
        invariants.append(
            Invariant(
                iid,
                "Every reachable iteration of a terminating loop must make progress toward its termination condition; a continue branch must not bypass the loop-counter or termination-state update.",
                "loop progress / termination invariant",
                0.87,
            )
        )
        hypotheses.append(
            Hypothesis(
                hid,
                f"{function_name} may become non-terminating when a reachable continue branch bypasses the loop's progress update and re-evaluates the same iteration state.",
                iid,
                function_name,
                "an external caller able to reach the loop with an input/state satisfying the continue condition",
                "the target call consumes gas or fails to complete instead of advancing to the next input element",
                evidence_ids=(f"E-MODEL-{function_name}",),
            )
        )

    return ControlFlowContribution(tuple(invariants), tuple(hypotheses))
