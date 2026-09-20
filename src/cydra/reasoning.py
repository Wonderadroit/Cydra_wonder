from __future__ import annotations

from pathlib import Path
import re

from .experiment_planning import plan_experiment as _plan_experiment
from .models import Evidence, Experiment, Hypothesis, Invariant, ContractModel, FunctionModel


_FUNCTION_SIGNATURE_RE = re.compile(r"\bfunction\s+(?P<name>\w+)\s*\((?P<parameters>[^)]*)\)\s*(?P<tail>[^\{;]*)\{", re.MULTILINE)
_DECLARED_MODIFIER_EXCLUSIONS = {"public", "external", "internal", "private", "view", "pure", "payable", "virtual", "override", "returns", "memory", "calldata", "storage"}
_CALLER_SCOPED_WRITE_RE = re.compile(r"\b[A-Za-z_]\w*\s*\[[^\]]*\b(?:msg\.sender|_msgSender\(\)|tx\.origin)\b[^\]]*\](?:\s*\[[^\]]*\])*\s*(?:\+?=|-=|\*=|/=|%=|\+\+|--)")
_CALLER_TOKEN_RE = re.compile(r"\b(?:msg\.sender|_msgSender\(\)|tx\.origin)\b")
_CALLER_KEYED_READ_RE = re.compile(r"\b[A-Za-z_]\w*\s*\[[^\]]*\b(?:msg\.sender|_msgSender\(\)|tx\.origin)\b[^\]]*\](?:\s*\[[^\]]*\])*")
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
        identifiers = re.findall(r"\b[A-Za-z_]\w*\b", _strip_signature_comments(match.group("tail")))
        modifiers: list[str] = []
        for token in identifiers:
            if token == "returns" or token in {"override", "virtual"}:
                break
            if token not in _DECLARED_MODIFIER_EXCLUSIONS and token not in modifiers:
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
        if match.group("name") != function.name or source.count("\n", 0, match.start()) + 1 != function.line:
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
    return body is not None and bool(_CALLER_SCOPED_WRITE_RE.search(body))


def _has_caller_authorization_predicate(function: FunctionModel) -> bool:
    for predicate in function.authorization_predicates:
        residual = _CALLER_KEYED_READ_RE.sub(" ", predicate)
        if _CALLER_TOKEN_RE.search(residual):
            return True
    return False


def _state_changing_functions(contract: ContractModel) -> tuple[FunctionModel, ...]:
    return tuple(f for f in contract.functions if f.visibility in _STATE_CHANGING_VISIBILITIES and f.writes)


def _externally_callable_functions(contract: ContractModel) -> tuple[FunctionModel, ...]:
    return tuple(f for f in contract.functions if f.visibility in _STATE_CHANGING_VISIBILITIES)


def _admin_named_functions(contract: ContractModel) -> tuple[FunctionModel, ...]:
    return tuple(f for f in _state_changing_functions(contract) if f.name.startswith(_ADMIN_NAME_PREFIXES))


def access_control_invariant(contract: ContractModel, privileged_modifier: str | None = None) -> Invariant:
    if privileged_modifier is None:
        observed = sorted({m for f in _externally_callable_functions(contract) for m in _declared_modifiers(contract, f)})
        privileged_modifier = observed[0] if len(observed) == 1 else ("observed privileged authorization" if observed else "onlyGov")
    return Invariant("INV-AUTH-001", f"Administrative state-changing operations must enforce {privileged_modifier} authorization.", "structural sibling-function rule; modifier-bearing externally callable functions", 0.90)


def generate_access_control_hypotheses(contract: ContractModel) -> tuple[Hypothesis, ...]:
    admin_functions = _admin_named_functions(contract)
    declared = tuple((f, _declared_modifiers(contract, f)) for f in admin_functions)
    protected_functions = [f for f in _externally_callable_functions(contract) if _declared_modifiers(contract, f)]
    if not protected_functions and not admin_functions:
        return ()
    if protected_functions:
        observed = sorted({m for f in protected_functions for m in _declared_modifiers(contract, f)})
        invariant = access_control_invariant(contract, observed[0] if len(observed) == 1 else "observed privileged authorization")
    else:
        invariant = access_control_invariant(contract)
    return tuple(
        Hypothesis(f"H-AUTH-{f.name}", f"{f.name} may permit an unauthorized caller to mutate privileged state.", invariant.invariant_id, f.name, "arbitrary external caller", "privileged configuration or authorization state can be changed", evidence_ids=(f"E-MODEL-{f.name}",))
        for f, modifiers in declared
        if not modifiers and not _is_caller_scoped_write(contract, f) and not _has_caller_authorization_predicate(f)
    )


def initialization_invariant(contract: ContractModel) -> Invariant:
    return Invariant("INV-INIT-001", "Initialization must not allow an arbitrary caller to claim privileged initialization state after deployment.", "lifecycle rule; initializer function and privileged state assignment", 0.90)


def generate_initialization_hypotheses(contract: ContractModel) -> tuple[Hypothesis, ...]:
    initializers = [f for f in contract.functions if f.name in {"initialize", "init"} and f.visibility in {"public", "external"}]
    invariant = initialization_invariant(contract)
    return tuple(Hypothesis(f"H-INIT-{f.name}", f"{f.name} may be callable in the deployed uninitialized state by an arbitrary caller, allowing privileged initialization state to be claimed.", invariant.invariant_id, f.name, "arbitrary external caller", "attacker-controlled initialization or privileged state", evidence_ids=(f"E-MODEL-{f.name}",)) for f in initializers)


def arithmetic_rounding_invariant(contract: ContractModel) -> Invariant | None:
    from .structural_arithmetic import arithmetic_rounding_invariant as _detect
    return _detect(contract)


def generate_arithmetic_hypotheses(contract: ContractModel) -> tuple[Hypothesis, ...]:
    from .structural_arithmetic import generate_arithmetic_hypotheses as _generate
    return _generate(contract)


def weighted_average_rounding_invariant(contract: ContractModel) -> Invariant | None:
    from .structural_rounding import weighted_average_rounding_invariant as _detect
    return _detect(contract)


def generate_weighted_average_rounding_hypotheses(contract: ContractModel) -> tuple[Hypothesis, ...]:
    from .structural_rounding import generate_weighted_average_rounding_hypotheses as _generate
    return _generate(contract)


def plan_access_control_experiment(hypothesis: Hypothesis) -> Experiment:
    return _plan_experiment(
        hypothesis,
        f"Execute {hypothesis.target_function} from an unprivileged actor and assert that the privileged state does not change; then repeat against the patched version.",
        ("missing authorization is exploitable", "authorization is enforced elsewhere"),
        1.0,
    )


def plan_initialization_experiment(hypothesis: Hypothesis) -> Experiment:
    return _plan_experiment(
        hypothesis,
        f"Deploy the target, call {hypothesis.target_function} as an arbitrary actor, and assert the actor cannot claim privileged initialization state; repeat against the patched version.",
        ("deployed lifecycle state is takeover-capable", "initializer is unavailable or safely initialized"),
        1.0,
    )


def plan_arithmetic_experiment(hypothesis: Hypothesis) -> Experiment:
    return _plan_experiment(
        hypothesis,
        f"Execute {hypothesis.target_function} with an arithmetic boundary input and assert the observed output equals the exact floor reference value; repeat against the patched version.",
        ("observed quote exceeds the exact floor", "observed quote equals the exact floor"),
        1.0,
    )


def plan_weighted_average_rounding_experiment(hypothesis: Hypothesis) -> Experiment:
    return Experiment(
        experiment_id=f"X-{hypothesis.hypothesis_id}",
        hypothesis_id=hypothesis.hypothesis_id,
        action=(
            f"Execute {hypothesis.target_function} with positive weighted-average inputs "
            "(100, 2, 99, 1) and assert the result is at least the mathematical ceiling."
        ),
        discriminates=(
            "weighted average rounds below its mathematical ceiling",
            "weighted average reaches the mathematical ceiling",
        ),
        cost=1.0,
        planned_inputs=("100", "2", "99", "1"),
    )


def build_evidence(contract: ContractModel, hypotheses: tuple[Hypothesis, ...]) -> tuple[Evidence, ...]:
    return tuple(Evidence(f"E-MODEL-{f.name}", "model", f"Function {f.name} has modifiers={list(_declared_modifiers(contract, f))} and writes={list(f.writes)}.", contract.source, f"line {f.line}") for f in contract.functions)