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

    # ERC1155-style minting can invoke an arbitrary receiver before a
    # protocol-specific aggregate (such as total supply) is updated.  A public
    # mapping getter is itself a read-only observation surface, so it can expose
    # the transient value during the receiver callback even though no explicit
    # view function is declared in the target contract.
    public_mapping = re.search(
        r"mapping\\s*\\([^)]*\\)\\s+public\\s+(?P<name>\\w+)\\s*;", source
    )
    if public_mapping and re.search(r"\\b(?:_mint|safeTransferFrom)\\s*\\(", source):
        mint_update = re.search(
            r"function\\s+(?P<name>_\\w*mint\\w*)\\s*\\([^)]*\\)[^{]*\\{(?P<body>.*?)\\n\\s*\\}",
            source,
            re.S,
        )
        if mint_update and re.search(
            rf"\\b{re.escape(public_mapping.group('name'))}\\s*\\[[^]]+\\][^;]*\\+=|\\b{re.escape(public_mapping.group('name'))}\\s*\\[[^]]+\\]\\[[^]]+\\][^;]*\\+=",
            mint_update.group("body"),
        ) and re.search(r"\\b(?:_mint|safeTransferFrom)\\s*\\(", mint_update.group("body")):
            target = mint_update.group("name")
            iid = f"INV-READONLY-REENTRANCY-{target}-mapping"
            hid = f"H-READONLY-{target}-mapping"
            invariants.append(
                Invariant(
                    iid,
                    "A public read-only observation must not expose an aggregate state value before the external token callback that can observe it has completed.",
                    "token callback ordering plus public mapping observation surface",
                    0.72,
                )
            )
            hypotheses.append(
                Hypothesis(
                    hid,
                    f"{target} may expose a stale aggregate through the public mapping getter during a token receiver callback because the aggregate is updated after the callback-capable mint operation.",
                    iid,
                    target,
                    "a receiver contract able to observe the public mapping getter during the token callback",
                    f"the public mapping getter returns a pre-update aggregate during {target} but the settled aggregate after {target} completes",
                    evidence_ids=(f"E-MODEL-{target}", f"E-MODEL-READONLY-MAPPING-{public_mapping.group('name')}"),
                )
            )

    return ReadOnlyReentrancyContribution(tuple(invariants), tuple(hypotheses))


def generate_cross_contract_read_only_reentrancy_hypotheses(
    contract: ContractModel, semantic=()
) -> ReadOnlyReentrancyContribution:
    """Find view functions that combine live state from external components.

    This surface is intentionally independent of Balancer/Curve names.  It looks
    for a public/external view that obtains a state vector from one external
    component and an independently queried denominator/supply/rate from another
    component, then combines them arithmetically without an observed context
    guard.  Such a view can be unsafe when called during an external component's
    state transition.
    """
    invariants: list[Invariant] = []
    hypotheses: list[Hypothesis] = []
    views = _view_functions(contract)
    try:
        source = Path(contract.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ReadOnlyReentrancyContribution((), ())

    for view in views:
        body = _body(contract, view)
        if not body or _lock_guarded(contract, view):
            continue
        external_reads = re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(", body)
        if len(external_reads) < 2:
            continue
        has_state_vector = bool(re.search(
            r"getPoolTokens|getBalances|getReserves|getAmounts|balances|reserves",
            body,
            re.I,
        ))
        has_supply_or_rate = bool(re.search(
            r"totalSupply|getRate|getVirtualSupply|getInvariant|virtualPrice|exchangeRate",
            body,
            re.I,
        ))
        has_combination = bool(re.search(
            r"[/ *]|return\s*\(",
            body,
        ))
        if not (has_state_vector and has_supply_or_rate and has_combination):
            continue

        iid = f"INV-READONLY-XCONTRACT-{view.name}"
        invariants.append(
            Invariant(
                iid,
                "A security or economic observation must not combine externally readable state from components while one component may be in an intermediate transition state.",
                "cross-contract external-read topology plus arithmetic state-derived observation",
                0.70,
            )
        )
        hypotheses.append(
            Hypothesis(
                f"H-READONLY-XCONTRACT-{view.name}",
                f"{view.name} may combine inconsistent externally sourced state during a callback, allowing a consumer to use a transient cross-contract value as if it represented settled state.",
                iid,
                view.name,
                "an external callback that occurs while one queried component is in an intermediate state",
                f"{view.name} can return a materially different state-derived value during the callback than after the external transition settles",
                evidence_ids=(f"E-MODEL-EXTERNAL-READS-{view.name}", f"E-MODEL-STATE-DERIVATION-{view.name}"),
            )
        )
    return ReadOnlyReentrancyContribution(tuple(invariants), tuple(hypotheses))
