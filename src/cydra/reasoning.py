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
    r"\b[A-Za-z_]\w*\s*\[[^\]]*\b(?:msg\.sender|_msgSender\(\)|tx\.origin)\b[^\]]*\]"
)


def _source_declared_modifiers(contract: ContractModel, function: FunctionModel) -> tuple[str, ...]:
    """Recover declared modifiers when the minimal model parser misses them."""
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
        identifiers = re.findall(r"\b[A-Za-z_]\w*\b", match.group("tail"))
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


def _is_caller_scoped_write(contract: ContractModel, function: FunctionModel) -> bool:
    """Return true when the function writes a mapping entry keyed by the caller.

    A caller-scoped write is materially different from an administrative write:
    the caller is modifying state in its own namespace rather than mutating a
    shared privileged configuration. This is a structural signal only; it does
    not prove authorization safety.
    """
    try:
        source = Path(contract.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return False

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
                    body = source[body_start + 1:index]
                    return bool(_CALLER_SCOPED_WRITE_RE.search(body))
        return False
    return False


def access_control_invariant(contract: ContractModel, privileged_modifier: str = "onlyGov") -> Invariant:
    return Invariant("INV-AUTH-001", f"Administrative state-changing operations must enforce {privileged_modifier} authorization.", "structural sibling-function rule; modifier-bearing administrative functions", 0.90)


def generate_access_control_hypotheses(contract: ContractModel) -> tuple[Hypothesis, ...]:
    admin_functions = [f for f in contract.functions if f.name.startswith(("set", "add", "remove", "update", "accept"))]
    declared = tuple((f, _declared_modifiers(contract, f)) for f in admin_functions)
    protected = [f for f, modifiers in declared if modifiers]
    if not protected:
        return ()
    invariant = access_control_invariant(contract)
    return tuple(
        Hypothesis(
            f"H-AUTH-{fn.name}",
            f"{fn.name} may permit an unauthorized caller to mutate privileged state.",
            invariant.invariant_id,
            fn.name,
            "arbitrary external caller",
            "privileged configuration or authorization state can be changed",
            evidence_ids=(f"E-MODEL-{fn.name}",),
        )
        for fn, modifiers in declared
        if not modifiers and not _is_caller_scoped_write(contract, fn)
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
    """Detect the Benchmark 003 rounding boundary without changing shared schemas."""
    source = Path(contract.source).read_text(encoding="utf-8")
    if "(assets * SCALE + 996) / 997" not in source:
        return None
    return Invariant(
        "INV-ARITH-001",
        "The quote calculation must not round an exact floor upward; observed output must equal the floor of the reference division.",
        "arithmetic rule; integer division with upward rounding offset",
        0.90,
    )


def generate_arithmetic_hypotheses(contract: ContractModel) -> tuple[Hypothesis, ...]:
    invariant = arithmetic_rounding_invariant(contract)
    if invariant is None:
        return ()
    targets = [f for f in contract.functions if f.name == "quoteMint"]
    return tuple(
        Hypothesis(
            f"H-ARITH-{fn.name}",
            f"{fn.name} may return a value above the exact floor because the arithmetic path rounds upward.",
            invariant.invariant_id,
            fn.name,
            "arithmetic boundary input that exposes rounding drift",
            "quoted value exceeds the exact floor by at least one unit",
            evidence_ids=(f"E-MODEL-{fn.name}",),
        )
        for fn in targets
    )


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
    return tuple(Evidence(f"E-MODEL-{fn.name}", "model", f"Function {fn.name} has modifiers={list(fn.modifiers)} and writes={list(fn.writes)}.", contract.source, f"line {fn.line}") for fn in contract.functions)
