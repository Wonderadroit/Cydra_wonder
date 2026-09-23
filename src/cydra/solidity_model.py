from __future__ import annotations

import re
from pathlib import Path

from .interface_resolver import ResolvedInterface, resolve_interface, resolve_named_type_source
from .models import ConstructorModel, ContractModel, FunctionModel, ParameterModel


_CONTRACT_RE = re.compile(r"\b(?:contract|library)\s+(?P<name>\w+)(?:\s+is\s+(?P<inherits>[^\{]+))?")
_PRAGMA_SOLIDITY_RE = re.compile(r"pragma\s+solidity\s+([^;]+);", re.MULTILINE)
_FUNCTION_RE = re.compile(
    r"\bfunction\s+(\w+)\s*\(([^)]*)\)\s*([^\{;]*)\{", re.MULTILINE
)
_CONSTRUCTOR_RE = re.compile(
    r"\bconstructor\s*\(([^)]*)\)\s*([^\{;]*)\{", re.MULTILINE
)
_INTERFACE_CAST_RE = re.compile(r"\b(I[A-Z]\w*)\s*\(")
_DECLARED_TYPE_RE = re.compile(
    r"^\s*(?:struct\s+(?P<struct>[A-Za-z_]\w*)\s*\{|"
    r"enum\s+(?P<enum>[A-Za-z_]\w*)\s*\{|"
    r"type\s+(?P<type>[A-Za-z_]\w*)\s+is\b)",
    re.MULTILINE,
)
_CALLER_TOKENS = ("msg.sender", "_msgSender()", "tx.origin")
_STATE_COMPARISON_RE = re.compile(
    r"\b(?P<name>[A-Za-z_]\w*)(?P<member>(?:\.[A-Za-z_]\w*)*)\s*"
    r"(?P<op>==|!=|>=|<=|>|<)\s*(?P<rhs>"
    r"(?:address|bytes\d+|uint\d*|int\d*)\s*\(\s*[^()]+\s*\)"
    r"|(?:[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)|0x[0-9A-Fa-f]+|\d+|true|false)"
)
_STATE_DECLARATION_RE = re.compile(
    r"^\s*(?P<type>mapping\s*\([^;]+\)|[A-Za-z_]\w*(?:\s*\[[^\]]*\])*)\s+"
    r"(?:(?:public|private|internal|external|constant|immutable|transient|override|virtual)\s+)*"
    r"(?P<name>[A-Za-z_]\w*)\s*(?:=.*)?$"
)
_STATE_DECLARATION_KEYWORDS = {
    "event", "error", "using", "struct", "enum", "function", "modifier", "constructor", "fallback", "receive",
}


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


def _balanced_parenthesized_end(source: str, opening: int) -> int:
    """Return the index immediately after a balanced parenthesized expression."""
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "(":
            depth += 1
        elif source[index] == ")":
            depth -= 1
            if depth == 0:
                return index + 1
    return len(source)


def _balanced_parenthesized_span(source: str, opening: int) -> tuple[str, int] | None:
    """Return an argument and matching close index for an opening parenthesis."""
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "(":
            depth += 1
        elif source[index] == ")":
            depth -= 1
            if depth == 0:
                return source[opening + 1 : index], index
    return None


def _interface_casts(source: str) -> tuple[tuple[str, str, int, int], ...]:
    """Find every interface cast using balanced parentheses, including nesting."""
    casts: list[tuple[str, str, int, int]] = []
    for match in _INTERFACE_CAST_RE.finditer(source):
        span = _balanced_parenthesized_span(source, match.end() - 1)
        if span is None:
            continue
        argument, closing = span
        casts.append((match.group(1), argument.strip(), match.start(), closing))
    return tuple(casts)


def _derived_dependency(
    argument: str,
    target_interface: str,
) -> tuple[str, str, str] | None:
    """Extract source-interface/method/target from a cast-return expression."""
    nested = _interface_casts(argument)
    for source_interface, _inner_argument, _start, closing in reversed(nested):
        suffix = argument[closing + 1 :].strip()
        method_match = re.match(r"^\.\s*([A-Za-z_]\w*)\s*\(", suffix)
        if method_match:
            return source_interface, method_match.group(1), target_interface
    return None


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


def _top_level_statements(body: str) -> tuple[str, ...]:
    """Return semicolon-terminated contract-body statements at brace depth zero."""
    statements: list[str] = []
    start = 0
    depth = 0
    for index, char in enumerate(body):
        if char == "{":
            depth += 1
        elif char == "}":
            depth = max(0, depth - 1)
        elif char == ";" and depth == 0:
            statement = body[start:index].strip()
            if statement:
                statements.append(statement)
            start = index + 1
    return tuple(statements)


def _state_variables(contract_body: str) -> tuple[str, ...]:
    """Inventory explicit state-variable names from one contract body.

    Only top-level declarations are considered. Function/local variables,
    struct members, events, errors, and other nested declarations are outside
    this inventory by construction.
    """
    variables: list[str] = []
    for statement in _top_level_statements(contract_body):
        match = _STATE_DECLARATION_RE.match(statement)
        if not match:
            continue
        type_token = match.group("type").split()[0]
        if type_token in _STATE_DECLARATION_KEYWORDS:
            continue
        # Constants and immutables are not mutable lifecycle state. Treating
        # their comparisons as state predicates can select a lifecycle
        # experiment merely because a constant appears in an input guard.
        if re.search(r"\b(?:constant|immutable)\b", statement):
            continue
        name = match.group("name")
        if name not in variables:
            variables.append(name)
    return tuple(variables)


def _state_predicate_polarities(body: str, state_variables: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    """Extract state predicates with conservative reachability polarity.

    A predicate in a require() must hold. A predicate guarding a revert in an
    if() must not hold for the normal path. Other if() branches remain unknown.
    """
    state_names = set(state_variables)
    results: list[tuple[str, str]] = []

    def add(candidate: str, polarity: str) -> None:
        for match in _STATE_COMPARISON_RE.finditer(candidate):
            if match.group("name") not in state_names:
                continue
            predicate = match.group(0).strip()
            item = (predicate, polarity)
            if item not in results:
                results.append(item)

    for match in re.finditer(r"\brequire\s*\(", body):
        opening = body.find("(", match.start())
        add(_first_argument(_balanced_parenthesized(body, opening)), "must_hold")

    for match in re.finditer(r"\bif\s*\(", body):
        opening = body.find("(", match.start())
        predicate = _balanced_parenthesized(body, opening).strip()
        # Solidity permits both braced and single-statement if bodies.
        # The function body has already been isolated, so the latter has no
        # branch brace to inspect. Only classify it when the next statement
        # is explicitly a revert; otherwise retain unknown polarity.
        after_predicate = body[_balanced_parenthesized_end(body, opening):].lstrip()
        polarity = "unknown"
        if after_predicate.startswith("{"):
            branch = _body(body, body.find("{", _balanced_parenthesized_end(body, opening)))
            if re.search(r"\brevert\b", branch):
                polarity = "must_not_hold"
        elif re.match(r"revert\s*(?:\(|;)", after_predicate):
            polarity = "must_not_hold"
        add(predicate, polarity)

    return tuple(results)


def _state_predicates(body: str, state_variables: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(predicate for predicate, _ in _state_predicate_polarities(body, state_variables))


def _execution_predicate_polarities(body: str, state_variables: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    """Extract path predicates that are not persistent-state predicates."""
    results: list[tuple[str, str]] = []
    state_names = set(state_variables)

    def add(candidate: str, polarity: str) -> None:
        text = candidate.strip()
        if not text:
            return
        identifiers = set(re.findall(r"\b[A-Za-z_]\w*\b", text))
        state_expression_words = {"length", "true", "false"}
        non_state = identifiers - state_names - state_expression_words
        if identifiers and not non_state:
            return
        item = (text, polarity)
        if item not in results:
            results.append(item)

    for match in re.finditer(r"\brequire\s*\(", body):
        opening = body.find("(", match.start())
        add(_first_argument(_balanced_parenthesized(body, opening)), "must_hold")

    for match in re.finditer(r"\bif\s*\(", body):
        opening = body.find("(", match.start())
        predicate = _balanced_parenthesized(body, opening).strip()
        tail_start = _balanced_parenthesized_end(body, opening)
        tail = body[tail_start:].lstrip()
        polarity = "unknown"
        if tail.startswith("{"):
            brace = body.find("{", tail_start)
            branch = _body(body, brace)
            if re.search(r"\brevert\b", branch):
                polarity = "must_not_hold"
        elif re.match(r"revert\s*(?:\(|;)", tail):
            polarity = "must_not_hold"
        add(predicate, polarity)

    return tuple(results)


def _execution_predicates(body: str, state_variables: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(predicate for predicate, _ in _execution_predicate_polarities(body, state_variables))


def _execution_value_bindings(body: str) -> tuple[tuple[str, str], ...]:
    """Extract conservative local assignments with call/data-flow expressions."""
    bindings: list[tuple[str, str]] = []
    # Match one assignment statement at a time. The previous expression-wide
    # regex could backtrack across `if`/`revert` text and invent bindings
    # such as `startDebt <- = 0) revert ...`. Keep the extractor deliberately
    # conservative: only statements beginning after a statement/brace boundary
    # are considered, and control-flow keywords cannot become declaration types.
    pattern = re.compile(
        r"(?:^|[;{}])\s*"
        r"(?!if\b|for\b|while\b|return\b|emit\b|revert\b)"
        r"(?:(?:[A-Za-z_]\w*(?:\s*\[[^\]]+\])?(?:\s+(?:memory|storage|calldata))?)\s+)?"
        r"(?P<name>[A-Za-z_]\w*)\s*=\s*(?P<expression>[^;{}]+);"
    )
    for match in pattern.finditer(body):
        name = match.group("name")
        expression = match.group("expression").strip()
        if expression and ("(" in expression or re.search(r"\b(?:msg|tx|block)\.", expression)):
            item = (name, expression)
            if item not in bindings:
                bindings.append(item)
    return tuple(bindings)


def _return_expressions(body: str) -> tuple[str, ...]:
    """Extract simple return expressions as conservative producer evidence."""
    expressions: list[str] = []
    for match in re.finditer(r"\breturn\s+([^;]+);", body):
        expression = match.group(1).strip()
        if expression and expression not in expressions:
            expressions.append(expression)
    return tuple(expressions)


def _declared_types(body: str) -> tuple[str, ...]:
    """Extract only contract-scope struct, enum, and value-type declarations."""
    declared: list[str] = []
    for match in _DECLARED_TYPE_RE.finditer(body):
        name = match.group("struct") or match.group("enum") or match.group("type")
        if name and name not in declared:
            declared.append(name)
    return tuple(declared)


def _inheritance_names(clause: str | None) -> tuple[str, ...]:
    """Extract base type names, dropping optional Solidity constructor arguments."""
    if not clause:
        return ()
    names: list[str] = []
    for item in _split_parameters(clause):
        item = item.strip()
        if not item:
            continue
        base = item.split("(", 1)[0].strip()
        if base and re.fullmatch(r"[A-Za-z_]\w*", base) and base not in names:
            names.append(base)
    return tuple(names)


def _project_root(path: Path) -> Path:
    """Find the project root used by interface resolution.

    A repository remappings file is authoritative when present. Small
    standalone fixtures without remappings use the directory containing the
    Solidity file, preserving the existing parser call shape.
    """
    resolved = path.resolve()
    for parent in (resolved.parent, *resolved.parents):
        if any((parent / marker).exists() for marker in ("remappings.txt", "foundry.toml", "package.json", ".git")):
            return parent
    return resolved.parent


def _constructor_interface_casts(
    body: str,
    parameters: tuple[ParameterModel, ...],
    *,
    importer: Path,
    root: Path,
) -> tuple[
    tuple[tuple[str, str], ...],
    tuple[tuple[str, ResolvedInterface], ...],
    tuple[tuple[str, str, ResolvedInterface], ...],
]:
    """Extract simple dependencies and resolved derived dependencies.

    The legacy ``interface_casts`` field intentionally remains limited to
    simple constructor-parameter casts so existing Foundry behavior is
    unchanged. ``resolved_interface_casts`` carries those same constructor
    dependencies with resolver metadata. Compound casts are represented as
    derived relationships and carry the resolved target interface.
    """
    parameter_names = {parameter.name for parameter in parameters if parameter.name}
    casts: list[tuple[str, str]] = []
    resolved_casts: list[tuple[str, ResolvedInterface]] = []
    derived_casts: list[tuple[str, str, ResolvedInterface]] = []
    seen_simple: set[tuple[str, str]] = set()
    seen_derived: set[tuple[str, str, str]] = set()

    for interface_name, argument, _start, _closing in _interface_casts(body):
        if re.fullmatch(r"\w+", argument):
            parameter_name = argument
            key = (parameter_name, interface_name)
            if parameter_name not in parameter_names or key in seen_simple:
                continue
            seen_simple.add(key)
            resolved = resolve_interface(root, importer, interface_name)
            casts.append(key)
            resolved_casts.append((parameter_name, resolved))
            continue

        derived = _derived_dependency(argument, interface_name)
        if derived is None:
            continue
        key = derived
        if key in seen_derived:
            continue
        seen_derived.add(key)
        resolved = resolve_interface(root, importer, interface_name)
        derived_casts.append((derived[0], derived[1], resolved))

    return tuple(casts), tuple(resolved_casts), tuple(derived_casts)


def _inherited_functions(
    root: Path,
    importer: Path,
    inherits: tuple[str, ...],
    seen: set[Path] | None = None,
) -> tuple[FunctionModel, ...]:
    """Resolve concrete inherited functions through the source inheritance graph."""
    seen = set() if seen is None else seen
    functions: list[FunctionModel] = []
    for inherited_name in inherits:
        try:
            source_path, _method = resolve_named_type_source(root, importer, inherited_name)
        except (FileNotFoundError, ValueError):
            continue
        resolved_path = (root / source_path).resolve()
        if resolved_path in seen:
            continue
        seen.add(resolved_path)
        try:
            contracts = parse_solidity(resolved_path, include_inherited=False)
        except (OSError, UnicodeError):
            continue
        base = next((item for item in contracts if item.name == inherited_name), None)
        if base is None:
            continue
        functions.extend(base.functions)
        functions.extend(_inherited_functions(root, resolved_path, base.inherits, seen))
    deduped: list[FunctionModel] = []
    seen_keys: set[tuple[str, int, str]] = set()
    for function in functions:
        key = (function.name, function.line, function.visibility)
        if key not in seen_keys:
            seen_keys.add(key)
            deduped.append(function)
    return tuple(deduped)


def parse_solidity(path: str | Path, *, include_inherited: bool = True) -> tuple[ContractModel, ...]:
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
        contract_name = contract_match.group("name")
        inherits = _inheritance_names(contract_match.group("inherits"))
        contract_start = contract_match.end()
        next_contract = _CONTRACT_RE.search(parse_source, contract_start)
        contract_source = parse_source[contract_start : next_contract.start() if next_contract else len(parse_source)]
        functions: list[FunctionModel] = []

        contract_opening = contract_source.find("{")
        contract_body = _body(contract_source, contract_opening) if contract_opening >= 0 else contract_source
        state_variables = _state_variables(contract_body)
        declared_types = _declared_types(contract_body)
        inherited_resolved_interfaces: list[ResolvedInterface] = []
        for inherited_name in inherits:
            try:
                inherited = resolve_interface(root, path, inherited_name)
            except (FileNotFoundError, ValueError):
                continue
            if inherited.name not in {item.name for item in inherited_resolved_interfaces}:
                inherited_resolved_interfaces.append(inherited)

        constructor = None
        constructor_match = _CONSTRUCTOR_RE.search(contract_source)
        if constructor_match:
            parameters = _parameters(constructor_match.group(1))
            body = _body(contract_source, constructor_match.end() - 1)
            interface_casts, resolved_interface_casts, derived_interface_casts = _constructor_interface_casts(
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
                derived_interface_casts=derived_interface_casts,
            )

        for match in _FUNCTION_RE.finditer(contract_source):
            name = match.group(1)
            parameter_text = match.group(2)
            signature_tail = match.group(3)
            opening = match.end() - 1
            body = _body(contract_source, opening)
            solidity_signature_keywords = {
                "public", "external", "internal", "private", "view", "pure",
                "payable", "virtual", "override", "returns", "memory", "calldata",
                "storage", "immutable", "constant",
            }
            modifier_tokens = []
            depth = 0
            for token_match in re.finditer(r"[A-Za-z_]\w*|[()]", signature_tail):
                token = token_match.group(0)
                if token == "(":
                    depth += 1
                    continue
                if token == ")":
                    depth = max(0, depth - 1)
                    continue
                if depth == 0 and token not in solidity_signature_keywords:
                    modifier_tokens.append(token)
            modifiers = tuple(modifier_tokens)
            visibility_match = re.search(r"\b(public|external|internal|private)\b", signature_tail)
            visibility = visibility_match.group(1) if visibility_match else "unspecified"
            write_candidates = re.findall(
                r"\b(\w+)\s*(?:(?:\[(?:[^\[\]]|\[[^\[\]]*\])*\])*)"
                r"\s*(?:=(?!=)|\+=|-=|\*=|/=|%=|\+\+|--)",
                body,
            )
            # State-model writes are explicit contract-state transitions, not local assignments.
            writes = tuple(sorted(set(name for name in write_candidates if name in state_variables)))
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
                    state_predicates=_state_predicates(body, state_variables),
                    state_predicate_polarities=_state_predicate_polarities(body, state_variables),
                    execution_predicates=_execution_predicates(body, state_variables),
                    execution_predicate_polarities=_execution_predicate_polarities(body, state_variables),
                    execution_value_bindings=_execution_value_bindings(body),
                    return_expressions=_return_expressions(body),
                )
            )

        contracts.append(
            ContractModel(
                name=contract_name,
                source=str(path),
                functions=tuple(functions),
                constructor=constructor,
                pragma=pragma,
                state_variables=state_variables,
                inherits=inherits,
                declared_types=declared_types,
                inherited_resolved_interfaces=tuple(inherited_resolved_interfaces),
                inherited_functions=_inherited_functions(root, path, inherits) if include_inherited else (),
            )
        )

    return tuple(contracts)
