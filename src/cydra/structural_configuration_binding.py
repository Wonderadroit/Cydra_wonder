from __future__ import annotations

import re
from pathlib import Path

from .models import ContractModel, Hypothesis, Invariant


_MAPPING_RE = re.compile(
    r"\bmapping\s*\(\s*[^;{}]+?\s*=>\s*[^;{}]+?\)\s+"
    r"(?P<name>[A-Za-z_]\w*)\s*;",
    re.MULTILINE,
)
_FUNCTION_RE = re.compile(
    r"\bfunction\s+(?P<name>\w+)\s*\([^)]*\)\s*(?P<tail>[^\{;]*)\{",
    re.MULTILINE,
)
_MAPPING_ACCESS_RE = re.compile(
    r"\b(?:[A-Za-z_]\w*\.)?(?P<mapping>[A-Za-z_]\w*)\s*"
    r"\[\s*(?P<key>[^\]]+)\s*\]\s*\.\s*(?P<field>[A-Za-z_]\w*)"
)


def _source(contract: ContractModel) -> str:
    try:
        return Path(contract.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""


def _body(source: str, match: re.Match[str]) -> str:
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


def _strip_comments(source: str) -> str:
    source = re.sub(r"//[^\n]*", " ", source)
    return re.sub(r"/\*.*?\*/", " ", source, flags=re.DOTALL)


def _mapping_names(source: str) -> set[str]:
    return {match.group("name") for match in _MAPPING_RE.finditer(_strip_comments(source))}


def _has_explicit_key_guard(body: str, mapping_name: str, key: str) -> bool:
    key = re.escape(key.strip())
    mapping = re.escape(mapping_name)
    guard = re.compile(
        rf"(?:require|revert|if)\s*\([^;{{}}]*"
        rf"{mapping}\s*\[\s*{key}\s*\][^;{{}}]*\)",
        re.DOTALL,
    )
    return bool(guard.search(body))


def configuration_binding_invariant(contract: ContractModel) -> Invariant | None:
    source = _strip_comments(_source(contract))
    if not source:
        return None

    mappings = _mapping_names(source)
    for match in _FUNCTION_RE.finditer(source):
        if match.group("name") not in {f.name for f in contract.functions if f.visibility in {"public", "external"}}:
            continue
        body = _body(source, match)
        for access in _MAPPING_ACCESS_RE.finditer(body):
            mapping = access.group("mapping")
            if mapping not in mappings:
                continue
            if not _has_explicit_key_guard(body, mapping, access.group("key")):
                return Invariant(
                    "INV-CONFIG-BINDING-001",
                    "A configuration selected by an external key must be validated as an existing, intended configuration before its fields control an effectful operation; an absent key must not silently fall back to default values.",
                    "keyed configuration topology; mapping lookup followed by effectful use without an explicit key-validity guard",
                    0.78,
                )
    return None


def generate_configuration_binding_hypotheses(
    contract: ContractModel,
) -> tuple[Hypothesis, ...]:
    source = _strip_comments(_source(contract))
    invariant = configuration_binding_invariant(contract)
    if invariant is None:
        return ()

    public_functions = {
        f.name: f for f in contract.functions if f.visibility in {"public", "external"}
    }
    mappings = _mapping_names(source)
    hypotheses: list[Hypothesis] = []

    for match in _FUNCTION_RE.finditer(source):
        name = match.group("name")
        function = public_functions.get(name)
        if function is None:
            continue
        body = _body(source, match)
        seen: set[str] = set()
        for access in _MAPPING_ACCESS_RE.finditer(body):
            mapping = access.group("mapping")
            key = access.group("key").strip()
            field = access.group("field")
            if mapping not in mappings or field in seen:
                continue
            if _has_explicit_key_guard(body, mapping, key):
                continue
            seen.add(field)
            hypotheses.append(
                Hypothesis(
                    f"H-CONFIG-BINDING-{name}-{mapping}",
                    f"{name} may use fields from the keyed configuration {mapping}[{key}] without proving that the selected configuration exists or is intended, allowing a default configuration to alter the effectful result.",
                    invariant.invariant_id,
                    name,
                    "choose an external configuration key that has not been registered",
                    "the effectful operation uses default configuration values for an unregistered key",
                    evidence_ids=(f"E-MODEL-{name}",),
                )
            )
            break

    return tuple(hypotheses)
