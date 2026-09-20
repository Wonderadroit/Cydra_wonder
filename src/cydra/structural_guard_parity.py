from __future__ import annotations

from pathlib import Path

from .models import ContractModel, FunctionModel, Hypothesis, Invariant
from .pipeline import ReasoningContribution


def _body(contract: ContractModel, function: FunctionModel) -> str | None:
    try:
        source = Path(contract.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    marker = f"function {function.name}"
    start = source.find(marker)
    if start < 0:
        return None
    brace = source.find("{", start)
    if brace < 0:
        return None
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[brace + 1:index]
    return None


def _postcondition_calls(contract: ContractModel, function: FunctionModel) -> tuple[str, ...]:
    body = _body(contract, function) or ""
    # This is deliberately a call-site observation. It does not assume that the
    # called guard has any particular security meaning.
    calls = []
    for token in ("checkLiquidity", "requireLiquidity", "assertHealthy", "checkHealth"):
        if token + "(" in body:
            calls.append(token)
    return tuple(calls)


def generate_guard_parity_hypotheses(contract: ContractModel, semantic=()) -> ReasoningContribution:
    """Find externally callable state transitions that miss an observed peer postcondition.

    The detector is class-neutral: it learns a postcondition from sibling state-changing
    functions and reports only an inconsistency. It does not name a vulnerability class,
    target, exploit, or expected impact.
    """
    public = tuple(f for f in contract.functions if f.visibility in {"public", "external"} and f.writes)
    guarded = tuple(f for f in public if _postcondition_calls(contract, f))
    if not guarded:
        return ReasoningContribution((), ())

    invariants: list[Invariant] = []
    hypotheses: list[Hypothesis] = []
    guarded_calls = sorted({call for f in guarded for call in _postcondition_calls(contract, f)})

    for candidate in public:
        if candidate in guarded:
            continue
        peers = tuple(
            peer.name for peer in guarded
            if peer.name != candidate.name and set(candidate.writes) & set(peer.writes)
        )
        if not peers:
            continue
        invariant_id = f"INV-GUARD-PARITY-{candidate.name}"
        invariants.append(
            Invariant(
                invariant_id,
                "State-changing transitions sharing a state surface with guarded peers should preserve the observed postcondition before returning.",
                "sibling state-transition postcondition parity",
                0.78,
            )
        )
        hypotheses.append(
            Hypothesis(
                f"H-GUARD-{candidate.name}",
                f"{candidate.name} may return after mutating shared state without enforcing the postcondition observed in sibling transitions.",
                invariant_id,
                candidate.name,
                "arbitrary external caller able to reach the state transition",
                "the transition can leave the modeled state outside the postcondition enforced by sibling transitions",
                evidence_ids=(f"E-MODEL-{candidate.name}",),
                related_functions=peers,
            )
        )

    return ReasoningContribution(tuple(invariants), tuple(hypotheses))
