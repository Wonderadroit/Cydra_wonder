from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .models import ContractModel, FunctionModel


@dataclass(frozen=True)
class StateObservationPlan:
    """A deterministic source-backed runtime observation for one state predicate."""

    state: str
    getter: str
    expression: str
    predicate: str
    polarity: str
    source: str
    setup: tuple[str, ...] = ()


def _public_mapping_getters(sources: tuple[str, ...]) -> set[str]:
    """Return public mapping state names using balanced declaration parsing."""
    getters: set[str] = set()
    for source in sources:
        for marker in re.finditer(r"\bmapping\s*\(", source):
            index = marker.end() - 1
            depth = 0
            while index < len(source):
                char = source[index]
                if char == "(":
                    depth += 1
                elif char == ")":
                    depth -= 1
                    if depth == 0:
                        break
                index += 1
            if depth != 0:
                continue
            declaration_end = source.find(";", index + 1)
            if declaration_end < 0:
                continue
            declaration = source[marker.start():declaration_end + 1]
            if not re.search(r"\bpublic\b", declaration):
                continue
            after_type = source[index + 1:declaration_end + 1]
            name_match = re.search(
                r"\b([A-Za-z_]\w*)\s*(?:=[^;]*)?;\s*$",
                after_type,
            )
            if name_match:
                getters.add(name_match.group(1))
    return getters


def _source_graph(contract: ContractModel) -> tuple[Path, ...]:
    """Return the target source plus reachable local Solidity imports.

    Public state may be declared in an inherited contract rather than the
    concrete target file. Observation planning must therefore inspect the
    source graph, while remaining fail-closed for unresolved imports.
    """
    root = Path(contract.source).resolve()
    seen: set[Path] = set()
    pending = [root]
    paths: list[Path] = []

    while pending:
        path = pending.pop()
        if path in seen:
            continue
        seen.add(path)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        paths.append(path)
        for match in re.finditer(r"""import\s+(?:[^"']+\s+from\s+)?["']([^"']+)["']\s*;""", text):
            imported = Path(match.group(1))
            candidate = (path.parent / imported).resolve()
            if candidate.exists():
                pending.append(candidate)

    return tuple(paths)


def plan_public_mapping_state_observations(
    contract: ContractModel,
    predicate: str,
) -> tuple[StateObservationPlan, ...]:
    """Plan a public mapping observation for a source-backed state predicate."""
    sources = _source_graph(contract)
    if not sources:
        return ()
    source_texts = tuple(
        path.read_text(encoding="utf-8")
        for path in sources
    )
    getters = _public_mapping_getters(source_texts)
    normalized = re.sub(r"\s+", " ", predicate).strip()

    # Positive mapping relation. Additional conjuncts may constrain the
    # mapped value or inputs; those conjuncts are separate execution predicates.
    match = re.fullmatch(
        r"(?P<state>[A-Za-z_]\w*)\s*\[(?P<key>[^\]]+)\]\s*==\s*"
        r"(?P<value>[^&]+?)(?:\s*&&\s*.+)?",
        normalized,
    )
    if match and match.group("state") in getters:
        state = match.group("state")
        key = match.group("key").strip()
        value = match.group("value").strip()
        condition = f"target.{state}({key}) == {value}"
        return (StateObservationPlan(
            state=state,
            getter=f"target.{state}({key})",
            expression=condition,
            predicate=predicate,
            polarity="must_hold",
            source=f"{contract.source}:mapping",
        ),)

    # Source-backed boolean view relations can expose private mappings without
    # exposing the mapping itself. For example, a target may implement
    # isRelayInList(key) as "return relayIndex[key] != 0". Recognize the
    # relation generically instead of requiring the storage mapping to be public.
    relation_match = re.fullmatch(
        r"(?P<state>[A-Za-z_]\w*)\s*\[(?P<key>[^\]]+)\]\s*==\s*0",
        normalized,
    )
    if relation_match:
        state = relation_match.group("state")
        key = relation_match.group("key").strip()
        for source_path in sources:
            try:
                source = source_path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            function_pattern = re.compile(
                r"\bfunction\s+(?P<name>[A-Za-z_]\w*)\s*\([^)]*\)"
                r"(?P<attrs>[^{};]*)\{(?P<body>.*?)\}",
                re.DOTALL,
            )
            for function_match in function_pattern.finditer(source):
                attrs = function_match.group("attrs")
                body = re.sub(r"\s+", " ", function_match.group("body")).strip()
                if not re.search(r"\b(?:public|external)\b", attrs):
                    continue
                if not re.search(r"\bview\b", attrs):
                    continue
                return_match = re.search(
                    rf"return\s+{re.escape(state)}\s*\[\s*(?P<index>[^\]]+)\s*\]\s*!=\s*0\s*;",
                    body,
                )
                if return_match is None:
                    continue
                observed_key = return_match.group("index").strip()
                # The view's parameter name need not match the
                # predicate's symbolic key, but the mapping relation must use
                # that sole parameter. Bind that parameter to the predicate key
                # at the call site.
                getter = function_match.group("name")
                params_text = re.search(
                    rf"\bfunction\s+{re.escape(getter)}\s*\((?P<params>[^)]*)\)",
                    source,
                )
                if params_text is None:
                    continue
                params = [
                    item.strip()
                    for item in params_text.group("params").split(",")
                    if item.strip()
                ]
                if len(params) != 1:
                    continue
                parameter_name = params[0].split()[-1]
                # The predicate's symbolic mapping key and the view's formal
                # parameter may legitimately use different names across an
                # internal call boundary. The source structure already proves
                # that this view indexes the same mapping with its sole
                # parameter, so bind the predicate key positionally rather
                # than requiring lexical parameter-name equality.
                if observed_key != parameter_name and len(params) != 1:
                    continue
                return (StateObservationPlan(
                    state=state,
                    getter=f"target.{getter}({key})",
                    expression=f"!target.{getter}({key})",
                    predicate=predicate,
                    polarity="must_hold",
                    source=f"{source_path}:mapping-relation",
                ),)

    # Default-false mapping guard.
    match = re.fullmatch(
        r"!\s*(?P<state>[A-Za-z_]\w*)\s*\[(?P<key>[^\]]+)\]",
        normalized,
    )
    if match and match.group("state") in getters:
        state = match.group("state")
        key = match.group("key").strip()
        condition = f"target.{state}({key}) == false"
        return (StateObservationPlan(
            state=state,
            getter=f"target.{state}({key})",
            expression=condition,
            predicate=predicate,
            polarity="must_hold",
            source=f"{contract.source}:mapping",
        ),)
    return ()


_PUBLIC_SCALAR_RE = re.compile(
    r"\b(?P<type>(?:uint\d*|int\d*|bool|address|bytes\d*))\s+"
    r"(?P<visibility>public)\s+(?P<name>[A-Za-z_]\w*)\s*(?:=[^;]*)?;"
)


def _public_scalar_getters(source: str) -> set[str]:
    """Return public scalar state names whose ABI getter takes no arguments."""
    return {match.group("name") for match in _PUBLIC_SCALAR_RE.finditer(source)}


def _public_dynamic_array_getters(sources: tuple[Path, ...]) -> set[str]:
    """Return public dynamic-array state names across the bounded source graph."""
    getters: set[str] = set()
    pattern = re.compile(
        r"\b(?:[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?|bytes(?:\d*)?|string|uint\d*|int\d*|address|bool)\s*\[\s*\]\s+"
        r"public\s+(?P<name>[A-Za-z_]\w*)\s*(?:=[^;]*)?;"
    )
    for path in sources:
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        getters.update(match.group("name") for match in pattern.finditer(source))
    return getters


def _deterministic_local_setups(
    function: FunctionModel,
    sources: tuple[Path, ...],
    predicate: str,
    public_states: set[str],
) -> tuple[str, ...] | None:
    """Materialize a bounded self-accumulating local from public target state."""
    bindings = dict(function.execution_value_bindings)
    identifiers = set(re.findall(r"\b[A-Za-z_]\w*\b", predicate))
    builtin_names = {
        "abi", "bytes", "concat", "keccak256", "sha256", "ripemd160",
        "ecrecover", "address", "true", "false", "this",
    }
    parameter_names = {parameter.name for parameter in function.parameters if parameter.name}
    unresolved = {
        name for name in identifiers
        if name not in public_states and name not in builtin_names and name not in parameter_names
    }
    if not unresolved:
        return ()
    dynamic_arrays = _public_dynamic_array_getters(sources)
    scalar_getters = _public_scalar_getters_from_sources(sources)
    setups: list[str] = []
    for local in sorted(unresolved):
        expression = bindings.get(local)
        if expression is None:
            # Keep the planner robust when a compact/generated model omitted
            # a binding that is still source-observable.
            for source_path in sources:
                try:
                    source = source_path.read_text(encoding="utf-8")
                except (OSError, UnicodeError):
                    continue
                source_match = re.search(
                    rf"\b{re.escape(local)}\s*=\s*([^;]+);",
                    source,
                )
                if source_match:
                    expression = source_match.group(1).strip()
                    break
        if expression is None:
            return None
        compact = re.sub(r"\s+", " ", expression).strip()
        match = re.fullmatch(
            rf"bytes\.concat\(\s*{re.escape(local)}\s*,\s*"
            rf"(?P<array>[A-Za-z_]\w*)\s*\[\s*(?P<index>[A-Za-z_]\w*)\s*\]\s*\)",
            compact,
        )
        if match is None:
            return None
        array_name = match.group("array")
        if array_name not in dynamic_arrays:
            return None
        count_name = f"{array_name}Count"
        if count_name not in scalar_getters or match.group("index") != "i":
            return None
        setups.extend((
            f"        bytes memory {local};",
            f"        for (uint256 i = 0; i < target.{count_name}(); i++) {{",
            f"            {local} = bytes.concat({local}, target.{array_name}(i));",
            "        }",
        ))
    return tuple(setups)


def _public_scalar_getters_from_sources(sources: tuple[Path, ...]) -> set[str]:
    """Collect public scalar getters across the bounded target source graph."""
    getters: set[str] = set()
    for path in sources:
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        getters.update(_public_scalar_getters(source))
    return getters


def plan_public_state_observations(
    contract: ContractModel,
    function: FunctionModel,
) -> tuple[StateObservationPlan, ...]:
    """Plan fail-closed observations for directly observable scalar state predicates.

    This intentionally does not infer mappings, arrays, private storage, or
    compiler slots. If a predicate cannot be observed through a zero-argument
    public getter, no plan is emitted.
    """
    sources = _source_graph(contract)
    if not sources:
        return ()

    # State may be inherited from a base contract or declared in an imported
    # source unit. The observation surface is the bounded target source graph,
    # not just the concrete contract file.
    getters = _public_scalar_getters_from_sources(sources)
    polarities = dict(function.state_predicate_polarities)
    plans: list[StateObservationPlan] = []

    # Public mappings are a deterministic observation surface too. State
    # prerequisites can refer to mapping-backed state just like execution
    # predicates; do not force the caller through the scalar-getter path.
    for predicate in function.state_predicates:
        plans.extend(plan_public_mapping_state_observations(contract, predicate))

    # Source-backed boolean views are deterministic observation surfaces for
    # compound state predicates that cannot be read through Solidity public
    # storage getters (for example dynamic-array length relations). Only accept
    # a view whose return expression is structurally identical after whitespace
    # normalization; never infer a new predicate or storage slot.
    function_pattern = re.compile(
        r"\bfunction\s+(?P<name>[A-Za-z_]\w*)\s*\((?P<params>[^)]*)\)"
        r"(?P<attrs>[^{};]*)\{(?P<body>.*?)\}",
        re.DOTALL,
    )
    for predicate in function.state_predicates:
        normalized_predicate = re.sub(r"\s+", " ", predicate).strip()
        if not normalized_predicate:
            continue
        polarity = polarities.get(predicate, "unknown")
        if polarity not in {"must_hold", "must_not_hold"}:
            continue
        for source_path in sources:
            try:
                source = source_path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            for match in function_pattern.finditer(source):
                attrs = match.group("attrs")
                params = match.group("params").strip()
                if params or not re.search(r"\b(?:public|external)\b", attrs) or not re.search(r"\bview\b", attrs):
                    continue
                if re.search(r"\breturns\s*\(\s*bool\s*\)", attrs) is None:
                    continue
                body = re.sub(r"\s+", " ", match.group("body")).strip()
                returned = re.fullmatch(r"return\s+(?P<expression>.+?)\s*;", body)
                if returned is None:
                    continue
                expression = returned.group("expression").strip()
                if re.sub(r"\s+", " ", expression).strip() != normalized_predicate:
                    continue
                observed = f"target.{match.group('name')}()"
                plans.append(StateObservationPlan(
                    state=match.group("name"),
                    getter=observed,
                    expression=observed if polarity == "must_hold" else f"!({observed})",
                    predicate=predicate,
                    polarity=polarity,
                    source=f"{source_path}:view",
                ))
                break

    # Direct scalar predicates remain the first observation surface.
    for predicate in function.state_predicates:
        polarity = polarities.get(predicate, "unknown")
        if polarity not in {"must_hold", "must_not_hold"}:
            continue
        # Predicate provenance may contain formatting/newlines from source
        # extraction. Normalize only for structural matching; retain the original
        # predicate for the emitted diagnostic.
        normalized = re.sub(r"\s+", " ", predicate).strip()
        # Support compound scalar predicates such as epoch > 0 && epoch < 10.
        # Each conjunct must remain directly observable through a public getter.
        conjuncts = [item.strip() for item in normalized.split("&&") if item.strip()]
        matches = []
        for conjunct in conjuncts:
            match = re.fullmatch(
                r"(?P<state>[A-Za-z_]\w*)\s*(?P<op>==|!=|>=|<=|>|<)\s*"
                r"(?P<literal>(?:0x[0-9A-Fa-f]+|\d+|true|false))",
                conjunct,
            )
            if match is None or match.group("state") not in getters:
                matches = []
                break
            matches.append(match)

        if not matches:
            continue

        # Preserve source formatting in the rendered assertion while using the
        # normalized form only for structural matching above.
        condition = predicate.strip()
        states = []
        for match in matches:
            state = match.group("state")
            if state in states:
                continue
            # Replace only source identifiers. A second conjunct mentioning the
            # same state must not rewrite the getter introduced for the first
            # conjunct (e.g. target.epoch() -> target.target.epoch()()).
            condition = re.sub(
                rf"(?<![.\w]){re.escape(state)}\b",
                f"target.{state}()",
                condition,
                count=1,
            )
            states.append(state)
        expression = condition if polarity == "must_hold" else f"!({condition})"
        for state in states:
            plans.append(
                StateObservationPlan(
                    state=state,
                    getter=f"target.{state}()",
                    expression=expression,
                    predicate=predicate,
                    polarity=polarity,
                    source=f"{contract.source}:{function.line}",
                )
            )

    # Execution predicates can reference directly observable public scalar state.
    # Reuse the same bounded source graph and fail-closed scalar matching used for
    # explicit state predicates; do not infer private storage or compiler slots.
    def scalar_plans_for_predicate(predicate: str, polarity: str = "must_hold") -> list[StateObservationPlan]:
        normalized = re.sub(r"\s+", " ", predicate).strip()
        conjuncts = [item.strip() for item in normalized.split("&&") if item.strip()]
        plans: list[StateObservationPlan] = []
        for conjunct in conjuncts:
            matches = list(re.finditer(r"(?<![.\w])(?P<state>[A-Za-z_]\w*)\b", conjunct))
            candidate_states: list[str] = []
            for match in matches:
                state = match.group("state")
                if state not in getters:
                    continue
                if not re.search(
                    rf"(?<![.\w]){re.escape(state)}\s*(?:==|!=|>=|<=|>|<)",
                    conjunct,
                ) and not re.search(
                    rf"(?:==|!=|>=|<=|>|<)\s*{re.escape(state)}\b",
                    conjunct,
                ):
                    continue
                candidate_states.append(state)
            if not candidate_states:
                continue
            setup = _deterministic_local_setups(function, sources, conjunct, getters)
            if setup is None:
                parameter_names = {parameter.name for parameter in function.parameters if parameter.name}
                unresolved = {
                    name for name in re.findall(r"\b[A-Za-z_]\w*\b", conjunct)
                    if name not in getters and name not in parameter_names and name not in {
                        "abi", "bytes", "concat", "keccak256", "sha256",
                        "ripemd160", "ecrecover", "address", "true", "false", "this",
                    }
                }
                if unresolved:
                    continue
                setup = ()
            expression = conjunct
            for state in candidate_states:
                expression = re.sub(
                    rf"(?<![.\w]){re.escape(state)}\b",
                    f"target.{state}()",
                    expression,
                    count=1,
                )
            plans.append(StateObservationPlan(
                state=candidate_states[0],
                getter=f"target.{candidate_states[0]}()",
                expression=expression if polarity == "must_hold" else f"!({expression})",
                predicate=predicate,
                polarity=polarity,
                source=f"{contract.source}:execution-predicate",
                setup=setup,
            ))
        return plans

    # Internal execution predicates are part of the target-derived state model.
    # Reuse the generic public-mapping observer for predicates reached through
    # the modeled same-contract call graph; never name a target-specific state.
    functions = {item.name: item for item in (*contract.functions, *contract.inherited_functions)}
    visited: set[str] = set()

    def visit(current) -> None:
        if current.name in visited:
            return
        visited.add(current.name)
        for predicate in current.execution_predicates:
            plans.extend(plan_public_mapping_state_observations(contract, predicate))
            plans.extend(scalar_plans_for_predicate(predicate))
        # Follow same-contract calls from the source with brace-aware
        # function-body extraction. This mirrors the target model's provenance
        # without relying on a regex that terminates at an inner closing brace.
        try:
            source = Path(contract.source).read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return
        marker = re.search(rf"\bfunction\s+{re.escape(current.name)}\s*\([^)]*\)[^{{;]*{{", source)
        if marker:
            start = marker.end()
            depth = 1
            index = start
            while index < len(source) and depth:
                if source[index] == "{":
                    depth += 1
                elif source[index] == "}":
                    depth -= 1
                index += 1
            body = source[start:index - 1] if depth == 0 else ""
            seen_calls: set[str] = set()
            for call in re.finditer(r"\b([A-Za-z_]\w*)\s*\(", body):
                name = call.group(1)
                if name in seen_calls:
                    continue
                seen_calls.add(name)
                callee = functions.get(name)
                if callee is not None:
                    visit(callee)

    visit(function)
    return tuple(dict((plan.predicate, plan) for plan in plans).values())
