from __future__ import annotations

import re
from pathlib import Path

from .models import ContractModel, Hypothesis


_FUNCTION_RE = re.compile(r"\bfunction\s+(?P<name>\w+)\s*\([^)]*\)\s*(?P<tail>[^\{;]*)\{", re.MULTILINE)
_VISIBILITIES = {"public", "external"}
_CALLER_TOKEN_RE = re.compile(r"\b(?:msg\.sender|_msgSender\(\)|tx\.origin)\b")
_CALLER_KEYED_READ_RE = re.compile(r"\b[A-Za-z_]\w*\s*\[[^\]]*\b(?:msg\.sender|_msgSender\(\)|tx\.origin)\b[^\]]*\](?:\s*\[[^\]]*\])*\s*")
_STATE_WRITE_RE = re.compile(
    r"\b(?P<name>[A-Za-z_]\w*)\s*(?:(?:\[[^\]]*\])|(?:\.[A-Za-z_]\w*))*\s*"
    r"(?P<op>=|\+=|-=|\*=|/=|%=|\+\+|--)"
)
_STATE_DECL_RE = re.compile(
    r"^\s*(?P<type>mapping\s*\([^;]+\)|[A-Za-z_]\w*(?:\s*\[[^\]]*\])*)\s+"
    r"(?:(?:public|private|internal|external|constant|immutable|transient|override|virtual)\s+)*"
    r"(?P<name>[A-Za-z_]\w*)\s*(?:=.*)?$"
)
_STATE_KEYWORDS = {"event", "error", "using", "struct", "enum", "function", "modifier", "constructor", "fallback", "receive"}


def _strip_comments(source: str) -> str:
    """Blank Solidity comments while preserving line/character positions."""
    chars = list(source)
    i = 0
    quote: str | None = None
    while i < len(source):
        char = source[i]
        if quote is not None:
            if char == "\\":
                i += 2
                continue
            if char == quote:
                quote = None
            i += 1
            continue
        if char in {"'", '"'}:
            quote = char
            i += 1
            continue
        if char == "/" and i + 1 < len(source) and source[i + 1] == "/":
            chars[i] = chars[i + 1] = " "
            i += 2
            while i < len(source) and source[i] != "\n":
                chars[i] = " "
                i += 1
            continue
        if char == "/" and i + 1 < len(source) and source[i + 1] == "*":
            chars[i] = chars[i + 1] = " "
            i += 2
            while i < len(source):
                if i + 1 < len(source) and source[i] == "*" and source[i + 1] == "/":
                    chars[i] = chars[i + 1] = " "
                    i += 2
                    break
                if source[i] != "\n":
                    chars[i] = " "
                i += 1
            continue
        i += 1
    return "".join(chars)


def _source_contract_state_names(contract: ContractModel) -> tuple[str, ...]:
    """Recover contract-scope state roots independently of the minimal model parser."""
    try:
        source = _strip_comments(Path(contract.source).read_text(encoding="utf-8"))
    except (OSError, UnicodeError):
        return contract.state_variables
    contract_match = re.search(r"\bcontract\s+" + re.escape(contract.name) + r"\b[^\{]*\{", source)
    if not contract_match:
        return contract.state_variables
    depth = 1
    start = contract_match.end()
    names: list[str] = list(contract.state_variables)
    for index in range(start, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                break
            if depth == 1:
                start = index + 1
        elif char == ";" and depth == 1:
            statement = source[start:index].strip()
            match = _STATE_DECL_RE.match(statement)
            if match:
                name = match.group("name")
                type_token = match.group("type").split()[0]
                if type_token not in _STATE_KEYWORDS and name not in names:
                    names.append(name)
            start = index + 1
    return tuple(names)


def _source_function_body(contract: ContractModel, function) -> str:
    try:
        source = _strip_comments(Path(contract.source).read_text(encoding="utf-8"))
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
    """Return explicit state-root mutations visible in this function body."""
    body = _source_function_body(contract, function)
    if not body:
        return ()
    state_names = set(_source_contract_state_names(contract))
    writes: list[str] = []
    for match in _STATE_WRITE_RE.finditer(body):
        name = match.group("name")
        if name in state_names and name not in writes:
            writes.append(name)
    return tuple(writes)


def _declared_modifiers(contract: ContractModel, function) -> tuple[str, ...]:
    try:
        source = _strip_comments(Path(contract.source).read_text(encoding="utf-8"))
    except (OSError, UnicodeError):
        return ()
    for match in _FUNCTION_RE.finditer(source):
        if match.group("name") != function.name or source.count("\n", 0, match.start()) + 1 != function.line:
            continue
        tokens = re.findall(r"\b[A-Za-z_]\w*\b", match.group("tail"))
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
    protected: set[str] = set()
    for function in contract.functions:
        if function.visibility not in _VISIBILITIES or not _declared_modifiers(contract, function):
            continue
        protected.update(_source_state_writes(contract, function))
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
