from __future__ import annotations

from pathlib import Path
import re

from .models import Evidence, Experiment, Hypothesis, Invariant, ContractModel, FunctionModel


_FUNCTION_SIGNATURE_RE = re.compile(
    r"\bfunction\s+(?P<name>\w+)\s*\((?P<parameters>[^)]*)\)\s*(?P<tail>[^\{;]*)\{",
    re.MULTILINE,
)
_DECLARED_MODIFIER_EXCLUSIONS = {
    "public", "external", "internal", "private",
    "view", "pure", "payable", "virtual", "override",
    "returns", "memory", "calldata", "storage",
}
_CALLER_SCOPED_WRITE_RE = re.compile(
    r"\b[A-Za-z_]\w*\s*"
    r"\[[^\]]*\b(?:msg\.sender|_msgSender\(\)|tx\.origin)\b[^\]]*\]"
    r"(?:\s*\[[^\]]*\])*\s*"
    r"(?:\+?=|-=|\*=|/=|%=|\+\+|--)"
)
_CALLER_TOKEN_RE = re.compile(r"\b(?:msg\.sender|_msgSender\(\)|tx\.origin)\b")
_ADMIN_NAME_PREFIXES = ("set", "add", "remove", "update", "accept")
_STATE_CHANGING_VISIBILITIES = {"public", "external"}


def _strip_signature_comments(text: str) -> str:
    text = re.sub(r"//[^\n]*", " ", text)
    return re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)


def _source_declared_modifiers(contract: ContractModel, function: FunctionModel) -> tuple[str, ...]:
    try:
        source = Path(contract.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ()

    for match in _FUNCTION_SIGNATURE_RE.finditer(source):
        if match.group("name") != function.name:
            continue
        line = source.count("\n", 0, match.start()) + 1
        if line != function.line:
            continue
        tail = _strip_signature_comments(match.group("tail"))
        identifiers = re.findall(r"\b[A-Za-z_]\w*\b", tail)
        modifiers: list[str] = []
        for token in identifiers:
            if token == "returns" or token in {"override", "virtual"}:
                break
            if token in _DECLARED_MODIFIER_EXCLUSIONS:
                continue
            if token not in modifiers:
                modifiers.append(token)
        return tuple(modifiers)
    return ()


def _declared_modifiers(contract: ContractModel, function: FunctionModel) -> tuple[str, ...]:
    return function.modifiers or _source_declared_modifiers(contract, function)


def _function_body(contract: ContractModel, function: FunctionModel) -> str | None:
    try:
        source = Path(contract.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None

    for match in _FUNCTION_SIGNATURE_RE.finditer(source):
        if match.group("name") != function.name:
            continue
        line = source.count("\n", 0, match.start()) + 1
        if line != function.line:
            continue
        body_start = match.end() - 1
        depth = 0
        for index in range(body_start, len(source)):
            if source[index] == "{":
                depth += 1
            elif source[index] == "}":
                depth -= 1
                if depth == 0:
                    return source[body_start + 1:index]
        return None
    return None


def _is_caller_scoped_write(contract: ContractModel, function: FunctionModel) -> bool:
    body = _function_body(contract, function)
    if body is None:
        return False
    return bool(_CALLER_SCOPED_WRITE_RE.search(body))


def _has_caller_authorization_predicate(function: FunctionModel) -> bool:
    return any(_CALLER_TOKEN_RE.search(predicate) for predicate in function.authorization_predicates)


def _state_changing_functions(contract: ContractModel) -> tuple[FunctionModel, ...]:
    return tuple(
        function
        for function in contract.functions
        if function.visibility in _STATE_CHANGING_VISIBILITIES and function.writes
    )


def _externally_callable_functions(contract: ContractModel) -> tuple[FunctionModel, ...]:
    return tuple(
        function
        for function in contract.functions
        if function.visibility in _STATE_CHANGING_VISIBILITIES
    )


def _admin_named_functions(contract: ContractModel) -> tuple[FunctionModel, ...]:
    return tuple(
        function
        for function in _state_changing_functions(contract)
        if function.name.startswith(_ADMIN_NAME_PREFIXES)
    )


def access_control_invariant(contract: ContractModel, privileged_modifier: str | None = None) -> Invariant:
    if privileged_modifier is None:
        protected_functions = [
            function
            for function in _externally_callable_functions(contract)
            if _declared_modifiers(contract, function)
        ]
        observed = sorted({
            modifier
            for function in protected_functions
            for modifier in _declared_modifiers(contract, function)
        })
        if len(observed) == 1:
            privileged_modifier = observed[0]
        elif len(observed) > 1:
            privileged_modifier = "observed privileged authorization"
        else:
            privileged_modifier = "onlyGov"
    return Invariant(
        "INV-AUTH-001",
        f"Administrative state-changing operations must enforce {privileged_modifier} authorization.",
        "structural sibling-function rule; modifier-bearing externally callable functions",
        0.90,
    )


def generate_access_control_hypotheses(contract: ContractModel) -> tuple[Hypothesis, ...]:
    admin_functions = _admin_named_functions(contract)
    declared = tuple((function, _declared_modifiers(contract, function)) for function in admin_functions)

    # Structural protected-sibling evidence is preferred when present, but the
    # legacy name heuristic remains as a compatibility fallback. This keeps
    # existing evidence-generating behavior while the generalized detector is
    # being validated against historical programs.
    protected_functions = [
        function
        for function in _externally_callable_functions(contract)
        if _declared_modifiers(contract, function)
    ]
    candidate_functions: list[tuple[FunctionModel, tuple[str, ...]]] = list(declared)
    if protected_functions:
        protected_modifiers = sorted({
            modifier
            for function in protected_functions
            for modifier in _declared_modifiers(contract, function)
        })
        invariant = access_control_invariant(
            contract,
            protected_modifiers[0] if len(protected_modifiers) == 1 else "observed privileged authorization",
        )
    elif admin_functions:
        invariant = access_control_invariant(contract)
    else:
        return ()

    return tuple(
        Hypothesis(
            f"H-AUTH-{function.name}",
            f"{function.name} may permit an unauthorized caller to mutate privileged state.",
            invariant.invariant_id,
            function.name,
            "arbitrary external caller",
            "privileged configuration or authorization state can be changed",
            evidence_ids=(f"E-MODEL-{function.name}",),
        )
        for function, modifiers in candidate_functions
        if not modifiers
        and not _is_caller_scoped_write(contract, function)
        and not _has_caller_authorization_predicate(function)
    )


def initialization_invariant(contract: ContractModel) -> Invariant:
    return Invariant("INV-INIT-001", "Initialization must not allow an arbitrary caller to claim privileged initialization state after deployment.", "lifecycle rule; initializer function and privileged state assignment", 0.90)


def generate_initialization_hypotheses(contract: ContractModel) -> tuple[Hypothesis, ...]:
    initializers = [f for f in contract.functions if f.name in {"initialize", "init"} and f.visibility in {"public", "external"}]
    if not initializers:
        return ()
    invariant = initialization_invariant(contract)
    return tuple(Hypothesis(f"H-INIT-{fn.name}", f"{fn.name} may be callable in the deployed uninitialized state by an arbitrary caller, allowing privileged initialization state to be claimed.", invariant.invariant_id, fn.name, "arbitrary external caller", "attacker-controlled initialization or privileged state", evidence_ids=(f"E-MODEL-{fn.name}",)) for fn in initializers)


def arithmetic_rounding_invariant(contract: ContractModel) -> Invariant | None:
    """Compatibility wrapper; structural arithmetic detection owns discovery."""
    from .structural_arithmetic import detect_arithmetic_rounding
    return detect_arithmetic_rounding(contract)


def generate_arithmetic_hypotheses(contract: ContractModel) -> tuple[Hypothesis, ...]:
    """Compatibility wrapper; structural arithmetic detection owns discovery."""
    from .structural_arithmetic import generate_arithmetic_hypotheses as _generate
    return _generate(contract)


def plan_access_control_experiment(hypothesis: Hypothesis) -> Experiment:
    return Experiment(f"X-{hypothesis.hypothesis_id}", hypothesis.hypothesis_id, f"Execute {hypothesis.target_function} from an unprivileged actor and assert that the privileged state does not change; then repeat against the patched version.", ("missing authorization is exploitable", "authorization is enforced elsewhere"), 1.0)


def plan_initialization_experiment(hypothesis: Hypothesis) -> Experiment:
    return Experiment(f"X-{hypothesis.hypothesis_id}", hypothesis.hypothesis_id, f"Deploy the target, call {hypothesis.target_function} as an arbitrary actor, and assert the actor cannot claim privileged initialization state; repeat against the patched version.", ("deployed lifecycle state is takeover-capable", "initializer is unavailable or safely initialized"), 1.0)


def plan_arithmetic_experiment(hypothesis: Hypothesis) -> Experiment:
    if hypothesis.invariant_id != "INV-ARITH-001":
        raise ValueError(f"Unsupported invariant for arithmetic experiment: {hypothesis.invariant_id}")
    return Experiment(
        f"X-{hypothesis.hypothesis_id}",
        hypothesis.hypothesis_id,
        f"Execute {hypothesis.target_function} with an arithmetic boundary input and assert the observed output equals the exact floor reference value; repeat against the patched version.",
        ("observed quote exceeds the exact floor", "observed quote equals the exact floor"),
        1.0,
    )


def build_evidence(contract: ContractModel, hypotheses: tuple[Hypothesis, ...]) -> tuple[Evidence, ...]:
    return tuple(
        Evidence(
            f"E-MODEL-{fn.name}",
            "model",
            f"Function {fn.name} has modifiers={list(_declared_modifiers(contract, fn))} and writes={list(fn.writes)}.",
            contract.source,
            f"line {fn.line}",
        )
        for fn in contract.functions
    )
