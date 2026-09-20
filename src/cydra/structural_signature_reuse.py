from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .models import ContractModel, Hypothesis, Invariant


@dataclass(frozen=True)
class SignatureReuseContribution:
    invariants: tuple[Invariant, ...]
    hypotheses: tuple[Hypothesis, ...]


def _source(contract: ContractModel) -> str:
    try:
        return Path(contract.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""


def _body(source: str, name: str) -> str:
    marker = re.search(rf"\bfunction\s+{re.escape(name)}\s*\([^)]*\)[^{{;]*\{{", source, re.S)
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


def _called_helpers(body: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(re.findall(r"\b([A-Za-z_]\w*)\s*\(", body)))


def _stateful_claim_helper(source: str, body: str) -> tuple[str, str] | None:
    for helper in _called_helpers(body):
        helper_body = _body(source, helper)
        if not helper_body:
            continue
        # A state marker is written in the helper, but the helper does not
        # visibly reject the already-marked state before writing it.
        marker = re.search(
            r"(?P<expr>[A-Za-z_]\w*\s*\[[^\]]+\])\s*=\s*(?:true|1)\s*;",
            helper_body,
            re.I,
        )
        if not marker:
            continue
        prefix = helper_body[: marker.start()]
        marker_expr = re.sub(r"\s+", "", marker.group("expr"))
        if re.search(
            rf"(?:require|if)\s*\([^)]*{re.escape(marker_expr)}[^)]*(?:true|1)|"
            rf"{re.escape(marker_expr)}\s*(?:==|!=)\s*(?:true|1)",
            re.sub(r"\s+", "", prefix),
            re.I,
        ):
            continue
        return helper, marker_expr
    return None


def generate_signature_reuse_hypotheses(
    contract: ContractModel, semantic=()
) -> SignatureReuseContribution:
    source = _source(contract)
    invariants: list[Invariant] = []
    hypotheses: list[Hypothesis] = []

    for function in contract.functions:
        if function.visibility not in {"public", "external"}:
            continue
        body = _body(source, function.name)
        if not body:
            continue
        if not re.search(r"\b(?:signature|sig)\b|\brecover\s*\(", body, re.I):
            continue
        if not re.search(r"\b(?:recover|ecrecover|ECDSA\.[A-Za-z_]+|_recoverSigner)\s*\(", body, re.I):
            continue
        helper = _stateful_claim_helper(source, body)
        if helper is None:
            continue
        helper_name, marker_expr = helper

        iid = f"INV-SIGNATURE-REUSE-{function.name}"
        hid = f"H-SIGNATURE-REUSE-{function.name}"
        invariants.append(
            Invariant(
                iid,
                "A signed state-changing authorization that records a one-time consumption marker must reject reuse of an already-consumed authorization.",
                "signed authorization lifecycle / pre-state consumption guard",
                0.84,
            )
        )
        hypotheses.append(
            Hypothesis(
                hid,
                f"{function.name} may accept the same signed authorization more than once because its claim path writes a consumption marker through {helper_name} without an observed pre-state rejection for {marker_expr}.",
                iid,
                function.name,
                "an external caller who possesses one valid authorization and can submit it again before the signed authorization changes",
                "the same signed authorization can cause the value/state transition twice",
                evidence_ids=(f"E-MODEL-{function.name}", f"E-STATE-MARKER-{helper_name}"),
            )
        )

    return SignatureReuseContribution(tuple(invariants), tuple(hypotheses))
