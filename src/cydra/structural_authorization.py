from __future__ import annotations

import re
from pathlib import Path
from collections.abc import Iterable

from .models import ContractModel, Hypothesis
from .ast_dataflow import SemanticRelationshipEvidence
from .semantic_state_effects import build_state_effect_index, state_writes_for_function

_FUNCTION_RE = re.compile(r"\bfunction\s+(?P<name>\w+)\s*\([^)]*\)\s*(?P<tail>[^\{;]*)\{", re.MULTILINE)
_VISIBILITIES = {"public", "external"}
_CALLER_TOKEN_RE = re.compile(r"\b(?:msg\.sender|_msgSender\(\)|tx\.origin)\b")
_CALLER_KEYED_READ_RE = re.compile(r"\b[A-Za-z_]\w*\s*\[[^\]]*\b(?:msg\.sender|_msgSender\(\)|tx\.origin)\b[^\]]*\](?:\s*\[[^\]]*\])*\s*")
_STATE_WRITE_RE = re.compile(r"\b(?P<name>[A-Za-z_]\w*)\s*(?:(?:\[[^\]]*\])|(?:\.[A-Za-z_]\w*))*\s*(?P<op>=|\+=|-=|\*=|/=|%=|\+\+|--)")
_STATE_DECL_RE = re.compile(r"^\s*(?P<type>mapping\s*\([^;]+\)|[A-Za-z_]\w*(?:\s*\[[^\]]*\])*)\s+(?:(?:public|private|internal|external|constant|immutable|transient|override|virtual)\s+)*(?P<name>[A-Za-z_]\w*)\s*(?:=.*)?$")
_STATE_KEYWORDS = {"event", "error", "using", "struct", "enum", "function", "modifier", "constructor", "fallback", "receive"}


def _strip_comments(source: str) -> str:
    chars = list(source); i = 0; quote: str | None = None
    while i < len(source):
        char = source[i]
        if quote is not None:
            if char == "\\": i += 2; continue
            if char == quote: quote = None
            i += 1; continue
        if char in {"'", '"'}: quote = char; i += 1; continue
        if char == "/" and i + 1 < len(source) and source[i + 1] == "/":
            chars[i] = chars[i + 1] = " "; i += 2
            while i < len(source) and source[i] != "\n": chars[i] = " "; i += 1
            continue
        if char == "/" and i + 1 < len(source) and source[i + 1] == "*":
            chars[i] = chars[i + 1] = " "; i += 2
            while i < len(source):
                if i + 1 < len(source) and source[i] == "*" and source[i + 1] == "/": chars[i] = chars[i + 1] = " "; i += 2; break
                if source[i] != "\n": chars[i] = " "
                i += 1
            continue
        i += 1
    return "".join(chars)


def _source_contract_state_names(contract: ContractModel) -> tuple[str, ...]:
    try: source = _strip_comments(Path(contract.source).read_text(encoding="utf-8"))
    except (OSError, UnicodeError): return contract.state_variables
    match = re.search(r"\bcontract\s+" + re.escape(contract.name) + r"\b[^\{]*\{", source)
    if not match: return contract.state_variables
    depth = 1; start = match.end(); names = list(contract.state_variables)
    for index in range(start, len(source)):
        char = source[index]
        if char == "{": depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0: break
            if depth == 1: start = index + 1
        elif char == ";" and depth == 1:
            statement = source[start:index].strip(); found = _STATE_DECL_RE.match(statement)
            if found:
                name = found.group("name"); type_token = found.group("type").split()[0]
                if type_token not in _STATE_KEYWORDS and name not in names: names.append(name)
            start = index + 1
    return tuple(names)


def _source_function_body(contract: ContractModel, function) -> str:
    try: source = _strip_comments(Path(contract.source).read_text(encoding="utf-8"))
    except (OSError, UnicodeError): return ""
    for match in _FUNCTION_RE.finditer(source):
        if match.group("name") != function.name or source.count("\n", 0, match.start()) + 1 != function.line: continue
        depth = 1; body_start = match.end()
        for index in range(body_start, len(source)):
            if source[index] == "{": depth += 1
            elif source[index] == "}":
                depth -= 1
                if depth == 0: return source[body_start:index]
        return source[body_start:]
    return ""


def _source_state_writes(contract: ContractModel, function) -> tuple[str, ...]:
    body = _source_function_body(contract, function)
    if not body: return ()
    state_names = set(_source_contract_state_names(contract)); writes: list[str] = []
    for match in _STATE_WRITE_RE.finditer(body):
        name = match.group("name")
        if name in state_names and name not in writes: writes.append(name)
    return tuple(writes)


def _declared_modifiers(contract: ContractModel, function) -> tuple[str, ...]:
    try: source = _strip_comments(Path(contract.source).read_text(encoding="utf-8"))
    except (OSError, UnicodeError): return ()
    for match in _FUNCTION_RE.finditer(source):
        if match.group("name") != function.name or source.count("\n", 0, match.start()) + 1 != function.line: continue
        tokens = re.findall(r"\b[A-Za-z_]\w*\b", match.group("tail")); modifiers: list[str] = []
        for token in tokens:
            if token in {"returns", "override", "virtual"}: break
            if token not in {"public", "external", "internal", "private", "view", "pure", "payable"} and token not in modifiers: modifiers.append(token)
        return tuple(modifiers)
    return ()


def _has_caller_authorization_predicate(function) -> bool:
    return any(_CALLER_TOKEN_RE.search(_CALLER_KEYED_READ_RE.sub(" ", predicate)) for predicate in function.authorization_predicates)


def _writes_for(function, contract: ContractModel, semantic_effects: dict[str, tuple] | None) -> tuple[str, ...]:
    if semantic_effects is not None:
        semantic = state_writes_for_function(semantic_effects, function.name)
        if semantic is not None:
            return semantic
    return _source_state_writes(contract, function)


def generate_structural_access_control_hypotheses(
    contract: ContractModel,
    semantic_evidence: Iterable[SemanticRelationshipEvidence] | None = None,
) -> tuple[Hypothesis, ...]:
    """Find unguarded writers to storage also written by protected siblings.

    Compiler-backed state effects take precedence when supplied. If a function has
    no compiler evidence, reasoning falls back to the existing source-linked path;
    it never treats missing semantic evidence as proof of a write.
    """
    semantic_effects = build_state_effect_index(semantic_evidence) if semantic_evidence is not None else None
    protected: set[str] = set()
    for function in contract.functions:
        if function.visibility not in _VISIBILITIES or not _declared_modifiers(contract, function): continue
        protected.update(_writes_for(function, contract, semantic_effects))
    if not protected: return ()
    hypotheses: list[Hypothesis] = []
    for function in contract.functions:
        writes = _writes_for(function, contract, semantic_effects)
        if function.visibility not in _VISIBILITIES or not writes: continue
        if _declared_modifiers(contract, function) or _has_caller_authorization_predicate(function): continue
        if not protected.intersection(writes): continue
        hypotheses.append(Hypothesis(
            f"H-AUTH-{function.name}",
            f"{function.name} may permit an unauthorized caller to mutate state also controlled by a protected sibling.",
            "INV-AUTH-001", function.name, "arbitrary external caller",
            "state shared with a protected administrative path can be changed without its authorization mechanism",
            evidence_ids=(f"E-MODEL-{function.name}",),
        ))
    return tuple(hypotheses)
