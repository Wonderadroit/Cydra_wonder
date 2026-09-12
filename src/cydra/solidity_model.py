from __future__ import annotations

import re
from pathlib import Path

from .interface_resolver import ResolvedInterface, resolve_interface
from .models import ConstructorModel, ContractModel, FunctionModel, ParameterModel


_CONTRACT_RE = re.compile(r"\bcontract\s+(\w+)")
_PRAGMA_SOLIDITY_RE = re.compile(r"pragma\s+solidity\s+([^;]+);", re.MULTILINE)
_FUNCTION_RE = re.compile(
    r"\bfunction\s+(\w+)\s*\(([^)]*)\)\s*([^\{;]*)\{", re.MULTILINE
)
_CONSTRUCTOR_RE = re.compile(
    r"\bconstructor\s*\(([^)]*)\)\s*([^\{;]*)\{", re.MULTILINE
)
_INTERFACE_CAST_RE = re.compile(r"\b(I[A-Z]\w*)\s*\(\s*(\w+)\s*\)")
_CALLER_TOKENS = ("msg.sender", "_msgSender()", "tx.origin")


def _strip_comments(source: str) -> str:
    """Blank Solidity comments while preserving source length and line offsets."""
    result = list(source)
    index = 0
    length = len(source)
    quote = None

    while index < length:
        char = source[index]

        if quote is not None:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = None
            index += 1
            continue

        if char in {"'", '"'}:
            quote = char
            index += 1
            continue

        if char == "/" and index + 1 < length and source[index + 1] == "/":
            result[index] = " "
            result[index + 1] = " "
            index += 2
            while index < length and source[index] != "\n":
                result[index] = " "
                index += 1
            continue

        if char == "/" and index + 1 < length and source[index + 1] == "*":
            result[index] = " "
            result[index + 1] = " "
            index += 2
            while index < length:
                if index + 1 < length and source[index] == "*" and source[index + 1] == "/":
                    result[index] = " "
                    result[index + 1] = " "
                    index += 2
                    break
                if source[index] != "\n":
                    result[index] = " "
                index += 1
            continue

        index += 1

    return "".join(result)


def _line_number(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def _body(source: str, opening: int) -> str:
    depth = 0
    for i in range(opening, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[opening + 1 : i]
    return source[opening + 1 :]


def _split_parameters(parameters: str) -> tuple[str, ...]:
    """Split a parameter list without attempting to parse Solidity semantics."""
    parts: list[str] = []
    start = 0
    paren = bracket = angle = 0
    for index, char in enumerate(parameters):
        if char == "(":
            paren += 1
        elif char == ")":
            paren = max(0, paren - 1)
        elif char == "[":
            bracket += 1
        elif char == "]":
            bracket = max(0, bracket - 1)
        elif char == "<":
            angle += 1
        elif char == ">":
            angle = max(0, angle - 1)
        elif char == "," and paren == bracket == angle == 0:
            part = parameters[start:index].strip()
            if part:
                parts.append(part)
            start = index + 1
    final = parameters[start:].strip()
    if final:
        parts.append(final)
    return tuple(parts)


def _parameter_model(declaration: str) -> ParameterModel:
    tokens = declaration.split()
    if not tokens:
        return ParameterModel(name="", type="")

    data_location = None
    for location in ("memory", "calldata", "storage"):
        if location in tokens:
            data_location = location
            tokens.remove(location)
            break

    if len(tokens) == 1:
        return ParameterModel(name="", type=tokens[0], data_location=data_location)

    name = tokens[-1]
    parameter_type = " ".join(tokens[:-1])
    return ParameterModel(name=name, type=parameter_type, data_location=data_location)


def _parameters(parameter_text: str) -> tuple[ParameterModel, ...]:
    return tuple(_parameter_model(part) for part in _split_parameters(parameter_text))


def _balanced_parenthesized(source: str, opening: int) -> str:
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "(":
            depth += 1
        elif source[index] == ")":
            depth -= 1
            if depth == 0:
                return source[opening + 1 : index]
    return source[opening + 1 :]


def _first_argument(expression: str) -> str:
    """Return the first top-level argument from a call expression."""
    paren = bracket = angle = 0
    for index, char in enumerate(expression):
        if char == "(":
            paren += 1
        elif char == ")":
            paren = max(0, paren - 1)
        elif char == "[":
            bracket += 1
        elif char == "]":
            bracket = max(0, bracket - 1)
        elif char == "<":
            angle += 1
        elif char == ">":
            angle = max(0, angle - 1)
        elif char == "," and paren == bracket == angle == 0:
            return expression[:index].strip()
    return expression.strip()


def _authorization_predicates(body: str) -> tuple[str, ...]:
    """Extract caller-identity predicates without interpreting their meaning."""
    predicates: list[str] = []

    for match in re.finditer(r"\bif\s*\(", body):
        opening = body.find("(", match.start())
        predicate = _balanced_parenthesized(body, opening).strip()
        if any(token in predicate for token in _CALLER_TOKENS):
            predicates.append(predicate)

    for match in re.finditer(r"\brequire\s*\(", body):
        opening = body.find("(", match.start())
        predicate = _first_argument(_balanced_parenthesized(body, opening))
        if any(token in predicate for token in _CALLER_TOKENS):
            predicates.append(predicate)

    return tuple(dict.fromkeys(predicates))


def _project_root(path: Path) -> Path:
    """Find the project root used by interface resolution.

    A repository remappings file is authoritative when present. Small
    standalone fixtures without remappings use the directory containing the
    Solidity file, preserving the existing parser call shape.
    """
    resolved = path.resolve()
    for parent in (resolved.parent, *resolved.parents):
        if (parent / "remappings.txt").is_file():
            return parent
    return resolved.parent


def _constructor_interface_casts(
    body: str,
    parameters: tuple[ParameterModel, ...],
    *,
    importer: Path,
    root: Path,
) -> tuple[tuple[tuple[str, str], ...], tuple[tuple[str, ResolvedInterface], ...]]:
    """Extract casts while preserving the legacy name-only field and adding resolved data."""
    parameter_names = {parameter.name for parameter in parameters if parameter.name}
    casts: list[tuple[str, str]] = []
    resolved_casts: list[tuple[str, ResolvedInterface]] = []
    seen: set[tuple[str, str]] = set()
    for match in _INTERFACE_CAST_RE.finditer(body):
        interface_name, parameter_name = match.groups()
        key = (parameter_name, interface_name)
        if parameter_name not in parameter_names or key in seen:
            continue
        seen.add(key)
        resolved = resolve_interface(root, importer, interface_name)
        casts.append(key)
        resolved_casts.append((parameter_name, resolved))
    return tuple(casts), tuple(resolved_casts)


def parse_solidity(path: str | Path) -> tuple[ContractModel, ...]:
    """Minimal deterministic model extractor used before compiler integration.

    It intentionally extracts only syntactic facts needed by the current
    milestone. It is not a Solidity parser and must not be treated as one.
    Constructor interface casts are enriched through the declared-import
    resolver; no repository-wide interface search is performed here.
    """
    path = Path(path)
    root = _project_root(path)
    source = path.read_text(encoding="utf-8")
    parse_source = _strip_comments(source)
    pragma_match = _PRAGMA_SOLIDITY_RE.search(parse_source)
    pragma = pragma_match.group(1).strip() if pragma_match else None
    contracts: list[ContractModel] = []

    for contract_match in _CONTRACT_RE.finditer(parse_source):
        contract_name = contract_match.group(1)
        contract_start = contract_match.end()
        next_contract = _CONTRACT_RE.search(parse_source, contract_start)
        contract_source = parse_source[contract_start : next_contract.start() if next_contract else len(parse_source)]
        functions: list[FunctionModel] = []

        constructor = None
        constructor_match = _CONSTRUCTOR_RE.search(contract_source)
        if constructor_match:
            parameters = _parameters(constructor_match.group(1))
            body = _body(contract_source, constructor_match.end() - 1)
            interface_casts, resolved_interface_casts = _constructor_interface_casts(
                body,
                parameters,
                importer=path,
                root=root,
            )
            constructor = ConstructorModel(
                parameters=parameters,
                line=_line_number(source, contract_start + constructor_match.start()),
                interface_casts=interface_casts,
                resolved_interface_casts=resolved_interface_casts,
            )

        for match in _FUNCTION_RE.finditer(contract_source):
            name = match.group(1)
            parameter_text = match.group(2)
            signature_tail = match.group(3)
            opening = match.end() - 1
            body = _body(contract_source, opening)
            modifiers = tuple(
                token
                for token in re.findall(r"\b[A-Za-z_]\w*\b", signature_tail)
                if token in {"onlyGov", "onlyOwner", "onlyAdmin", "onlyKeeper", "onlyWhitelisted"}
            )
            visibility_match = re.search(r"\b(public|external|internal|private)\b", signature_tail)
            visibility = visibility_match.group(1) if visibility_match else "unspecified"
            writes = tuple(sorted(set(re.findall(r"\b(\w+)\s*(?:\[[^]]+\])?\s*=", body))))
            external_calls = tuple(sorted(set(re.findall(r"\b(\w+)\.(\w+)\s*\(", body))))
            functions.append(
                FunctionModel(
                    name=name,
                    visibility=visibility,
                    modifiers=modifiers,
                    writes=writes,
                    external_calls=external_calls,
                    line=_line_number(source, contract_start + match.start()),
                    parameters=_parameters(parameter_text),
                    authorization_predicates=_authorization_predicates(body),
                )
            )

        contracts.append(
            ContractModel(
                name=contract_name,
                source=str(path),
                functions=tuple(functions),
                constructor=constructor,
                pragma=pragma,
            )
        )

    return tuple(contracts)
