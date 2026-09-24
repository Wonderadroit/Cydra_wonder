from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .compiler_constraints import ConstraintEvidence
from .interface_resolver import resolve_interface, resolve_named_type_source, resolve_import, _imports_for, _strip_comments
from .models import ContractModel, FunctionModel
from .ast_dataflow import SemanticRelationshipEvidence
from .semantic_state_effects import build_state_effect_index, state_reads_for_function, state_writes_for_function


@dataclass(frozen=True)
class ExecutionRequirement:
    """A deterministic prerequisite for executing a modeled target action.

    This layer records what must be true for an experiment to be meaningful.
    It does not decide whether satisfying the requirement is safe, desirable,
    or evidence of a vulnerability.
    """

    kind: str
    subject: str
    source: str
    status: str = "required"
    detail: str = ""


@dataclass(frozen=True)
class SetupAction:
    """A verified, ordered state-setup transition."""
    function: str
    caller_role: str | None
    provenance: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExecutionReadiness:
    contract: str
    constructor_requirements: tuple[ExecutionRequirement, ...] = ()
    caller_requirements: tuple[ExecutionRequirement, ...] = ()
    runtime_requirements: tuple[ExecutionRequirement, ...] = ()
    state_requirements: tuple[ExecutionRequirement, ...] = ()
    state_setup_candidates: tuple[ExecutionRequirement, ...] = ()
    execution_requirements: tuple[ExecutionRequirement, ...] = ()

    @property
    def blockers(self) -> tuple[ExecutionRequirement, ...]:
        return tuple(
            item
            for item in (
                *self.constructor_requirements,
                *self.caller_requirements,
                *self.runtime_requirements,
                *self.state_requirements,
                *self.execution_requirements,
            )
            if item.status == "unresolved"
        )


_ROLE_HINTS = (
    ("owner", "owner"),
    ("admin", "admin"),
    ("guardian", "guardian"),
    ("riskmanager", "risk_manager"),
    ("risk_manager", "risk_manager"),
    ("liquidator", "liquidator"),
    ("tranche", "tranche"),
    ("factory", "factory"),
)


def _address_role(name: str) -> str | None:
    normalized = re.sub(r"[^a-z0-9]", "", name.lower())
    for needle, role in _ROLE_HINTS:
        if needle in normalized:
            return role
    return None


def role_address_expression(role: str) -> str | None:
    return {
        "owner": "address(0x1001)",
        "admin": "address(0x1002)",
        "guardian": "address(0x1003)",
        "risk_manager": "address(0x1004)",
        "liquidator": "address(0x1005)",
        "factory": "address(0x1006)",
        "tranche": "address(0x1007)",
    }.get(role)


def _constructor_requirements(contract: ContractModel) -> tuple[ExecutionRequirement, ...]:
    if contract.constructor is None:
        return ()

    requirements: list[ExecutionRequirement] = []
    source_path = Path(contract.source).resolve()
    project_root = next(
        (
            parent
            for parent in (source_path.parent, *source_path.parents)
            if any((parent / marker).exists() for marker in ("foundry.toml", "package.json", "remappings.txt"))
        ),
        source_path.parent,
    )

    def resolves_to_interface(type_name: str) -> bool:
        try:
            resolved = resolve_interface(project_root, source_path, type_name)
        except (FileNotFoundError, ValueError, OSError, UnicodeError):
            return False
        return bool(resolved.methods or resolved.name == type_name)
    for parameter in contract.constructor.parameters:
        base = parameter.type.strip().split()[0].rstrip("[]")
        primitive = base in {"address", "bool", "string", "bytes"} or base.startswith(
            ("uint", "int", "bytes")
        )
        interface_parameter = bool(
            contract.constructor
            and any(
                parameter.name == parameter_name
                for parameter_name, _interface_name in contract.constructor.interface_casts
            )
        ) or resolves_to_interface(base)
        if not primitive:
            requirements.append(
                ExecutionRequirement(
                    "constructor_dependency",
                    base,
                    "constructor",
                    "constraint" if interface_parameter else "required",
                    (
                        "interface-typed constructor input can be materialized by the generic "
                        "runtime stub; deployment remains part of experiment verification"
                        if interface_parameter
                        else f"constructor parameter {parameter.name or '<unnamed>'} uses a contract/interface/custom type"
                    ),
                )
            )
        if base == "address":
            role = _address_role(parameter.name)
            if role is not None:
                requirements.append(
                    ExecutionRequirement(
                        "constructor_role",
                        role,
                        f"constructor:{parameter.name}",
                        "constraint",
                        "constructor role is an experiment input binding; the generated deployment must materialize it",
                    )
                )
    return tuple(requirements)


def caller_role(function: FunctionModel) -> str | None:
    """Infer a deterministic role binding from a modeled authorization modifier."""
    for modifier in function.modifiers:
        role = _address_role(modifier)
        if role is not None:
            return role
    for predicate in function.authorization_predicates:
        role = _address_role(predicate)
        if role is not None:
            return role
    return None


def _caller_requirements(function: FunctionModel) -> tuple[ExecutionRequirement, ...]:
    requirements: list[ExecutionRequirement] = []
    for modifier in function.modifiers:
        # Lifecycle modifiers control initialization state, not caller identity.
        # Treating initializer/reinitializer/onlyInitializing as caller roles
        # creates a false prerequisite and blocks legitimate lifecycle tests.
        if modifier in {"initializer", "reinitializer", "onlyInitializing"}:
            continue
        if modifier.startswith(("returns", "override")):
            continue
        requirements.append(
            ExecutionRequirement(
                "caller_role",
                modifier,
                f"{function.name}:modifier",
                "required",
                "function signature declares a custom modifier",
            )
        )
    for predicate in function.authorization_predicates:
        requirements.append(
            ExecutionRequirement(
                "caller_predicate",
                predicate,
                f"{function.name}:body",
                "required",
                "function body checks caller identity",
            )
        )
    return tuple(dict.fromkeys(requirements))


def _runtime_receiver_is_library(contract: ContractModel, receiver: str) -> bool:
    """Resolve a call receiver and exclude deterministic library calls from runtime blockers."""
    source_path = Path(contract.source).resolve()
    project_root = next(
        (parent for parent in (source_path.parent, *source_path.parents) if (parent / "foundry.toml").exists()),
        source_path.parent,
    )
    try:
        resolved, _ = resolve_named_type_source(project_root, source_path, receiver)
        resolved_path = Path(resolved)
        if not resolved_path.is_absolute():
            resolved_path = (project_root / resolved_path).resolve()
        source = resolved_path.read_text(encoding="utf-8")
        return bool(re.search(r"\blibrary\s+" + re.escape(receiver) + r"\b", source))
    except (FileNotFoundError, ValueError, OSError, UnicodeError):
        # Fallback only through the import graph. Do not scan the whole repository:
        # state variables such as tranches are not type names and large dependency
        # trees must remain bounded.
        visited: set[Path] = set()

        def walk(path: Path) -> bool | None:
            path = path.resolve()
            if path in visited or not path.is_file():
                return None
            visited.add(path)
            try:
                source = _strip_comments(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError):
                return None
            if re.search(r"\blibrary\s+" + re.escape(receiver) + r"\b", source):
                return True
            if re.search(r"\b(?:contract|interface)\s+" + re.escape(receiver) + r"\b", source):
                return False
            for import_path in _imports_for(path):
                resolved_import = resolve_import(project_root, path, import_path)
                if resolved_import is None:
                    continue
                result = walk(resolved_import[0])
                if result is not None:
                    return result
            return None

        return walk(source_path) is True
def _resolved_interface_method(contract: ContractModel, receiver: str, method: str) -> bool:
    """Return True only when a receiver cast resolves to an interface declaring method."""
    match = re.match(r"^(?P<type>[A-Za-z_]\w*)\s*\(", receiver.strip())
    if not match:
        return False
    type_name = match.group("type")
    source_path = Path(contract.source).resolve()
    project_root = next(
        (parent for parent in (source_path.parent, *source_path.parents) if (parent / "foundry.toml").exists()),
        source_path.parent,
    )
    try:
        interface = resolve_interface(project_root, source_path, type_name)
    except (FileNotFoundError, ValueError, OSError, UnicodeError):
        return False
    return any(item.name == method for item in interface.methods)


def _runtime_requirements(contract: ContractModel, function: FunctionModel) -> tuple[ExecutionRequirement, ...]:
    requirements: list[ExecutionRequirement] = []
    state_names = set(contract.state_variables)
    for receiver, method in function.external_calls:
        # Solidity array mutations are represented by the parser as calls on
        # synthetic receivers, but push/pop are local state operations, not
        # runtime dependencies that need a stubbed external target.
        if method in {"push", "pop"}:
            continue
        if _runtime_receiver_is_library(contract, receiver):
            continue

        # A call through a state-backed receiver is not an unknown runtime
        # target: the target address is part of the target's own state/model.
        # Keep it as a prerequisite for runtime verification, but do not
        # misclassify it as an unconstructible external dependency.
        normalized_receiver = receiver.strip()
        receiver_root = re.match(r"^([A-Za-z_]\w*)$", normalized_receiver)
        configured = bool(receiver_root and receiver_root.group(1) in state_names)
        interface_call = _resolved_interface_method(contract, normalized_receiver, method)
        configured_cast = interface_call and any(
            token in state_names
            for token in re.findall(r"\b[A-Za-z_]\w*\b", normalized_receiver)
        )
        status = "discovered" if configured or configured_cast else "required"
        detail = (
            "external call receiver is a modeled contract state value; runtime behavior "
            "must still be verified against the target's configured dependency"
            if configured
            else "compiler/source-resolved interface method uses a modeled target state value; "
            "runtime behavior must still be verified against that configured address"
            if configured_cast
            else "function performs an external call whose target/state may be required for execution"
        )
        requirements.append(
            ExecutionRequirement(
                "runtime_dependency",
                f"{receiver}.{method}",
                f"{function.name}:external_call",
                status,
                detail,
            )
        )
    return tuple(dict.fromkeys(requirements))


def _execution_dataflow_requirements(
    contract: ContractModel,
    function: FunctionModel,
    semantic_evidence: tuple[SemanticRelationshipEvidence, ...] = (),
) -> tuple[ExecutionRequirement, ...]:
    """Resolve local execution bindings to modeled function producers when possible.

    Discovery of a producer is evidence about program data flow only. It does not
    establish that the producer can return the required value in a live fixture.
    """
    predicates = " ".join(function.execution_predicates)
    requirements: list[ExecutionRequirement] = []
    functions_by_name = {item.name: item for item in (*contract.inherited_functions, *contract.functions)}
    semantic_effects = build_state_effect_index(semantic_evidence)

    for local, expression in function.execution_value_bindings:
        if local not in predicates:
            continue

        pure_local_expression = not re.search(r"\b[A-Za-z_]\w*\s*\(", expression)
        dataflow_status = "constraint" if pure_local_expression else "required"
        dataflow_detail = (
            "deterministic local derivation used by an experiment constraint; "
            "the generated experiment must reproduce the derivation"
            if pure_local_expression
            else "execution predicate depends on a locally bound call/input value; "
            "the binding must be resolved before reachability is treated as satisfied"
        )
        requirements.append(
            ExecutionRequirement(
                "execution_dataflow",
                f"{local} <- {expression}",
                f"{function.name}:body",
                dataflow_status,
                dataflow_detail,
            )
        )

        call_match = re.match(r"^(?:[A-Za-z_]\w*\.)?(?P<name>[A-Za-z_]\w*)\s*\(", expression)
        if not call_match:
            continue
        producer_name = call_match.group("name")
        producer = functions_by_name.get(producer_name)
        member_call = re.match(
            r"^(?P<receiver>[A-Za-z_]\w*(?:\([^)]*\))?)\.\s*(?P<method>[A-Za-z_]\w*)\s*\(",
            expression,
        )
        if member_call and not _runtime_receiver_is_library(contract, member_call.group("receiver").split("(")[0]):
            requirements.append(
                ExecutionRequirement(
                    "execution_value_runtime_dependency",
                    f"{member_call.group('receiver')}.{member_call.group('method')}",
                    f"{function.name}:value-binding",
                    "unresolved",
                    "execution value is produced by a non-library member call whose target/state "
                    "must be resolved before the consumer is considered reachable",
                )
            )
        if producer is None:
            member_head = re.match(
                r"^(?P<receiver>[A-Za-z_]\w*(?:\([^)]*\))?)\.\s*(?P<method>[A-Za-z_]\w*)\s*\(",
                expression,
            )
            receiver_type = member_head.group("receiver").split("(")[0] if member_head else None
            if receiver_type is not None and _runtime_receiver_is_library(contract, receiver_type):
                continue
            # A call-shaped value binding whose producer is not present in the
            # local model is itself a reachability dependency. Fail closed
            # rather than allowing a setup writer to appear constructible.
            requirements.append(
                ExecutionRequirement(
                    "execution_value_dependency",
                    expression,
                    f"{function.name}:value-binding",
                    "unresolved",
                    "call-shaped execution value has no compiler/model-resolved local producer; "
                    "the value source must be resolved before reachability is treated as satisfied",
                )
            )
            continue

        returns = ", ".join(producer.return_expressions) if producer.return_expressions else "<return expression not modeled>"
        requirements.append(
            ExecutionRequirement(
                "execution_value_producer",
                f"{local} <- {producer.name}({returns})",
                f"{producer.name}:return",
                "discovered",
                "modeled local call-result producer; its dependencies and satisfiability "
                "must be resolved before the consuming path is treated as reachable",
            )
        )
        producer_reads = state_reads_for_function(semantic_effects, producer.name)
        # ERC-4626's maxWithdraw(owner) is bounded by balanceOf(owner). When
        # the consumer explicitly rejects a zero result, a non-zero caller
        # share balance is a deterministic prerequisite. This is a protocol-
        # agnostic semantic rule, not an Arcadia-specific assumption.
        local_polarities = dict(function.execution_predicate_polarities)
        needs_positive_result = any(
            re.search(rf"\b{re.escape(local)}\s*(?:==|<=)\s*0\b", predicate)
            and local_polarities.get(predicate) == "must_not_hold"
            for predicate in function.execution_predicates
        )
        if needs_positive_result and re.search(r"\bmaxWithdraw\s*\(\s*msg\.sender\s*\)", expression):
            balance_writers = []
            for candidate in (*contract.inherited_functions, *contract.functions):
                if candidate.name == function.name or candidate.visibility not in {"public", "external"}:
                    continue
                writes = state_writes_for_function(semantic_effects, candidate.name)
                if writes is not None and "balanceOf" in writes:
                    balance_writers.append(candidate.name)
            if balance_writers:
                requirements.append(
                    ExecutionRequirement(
                        "caller_state_dependency",
                        "balanceOf(msg.sender) > 0",
                        f"{producer.name}:erc4626-balance",
                        "discovered",
                        "standard ERC-4626 positive-withdraw path requires a non-zero caller share balance; compiler-backed state effects identify candidate transitions that can establish that balance: "
                        + ", ".join(sorted(set(balance_writers))),
                    )
                )
                for writer_name in sorted(set(balance_writers)):
                    requirements.append(
                        ExecutionRequirement(
                            "caller_state_setup_candidate",
                            writer_name,
                            f"{producer.name}:erc4626-balance",
                            "discovered",
                            "compiler-backed transition writes the producer's required caller balance state; its own prerequisites must be solved before execution",
                        )
                    )
            else:
                requirements.append(
                    ExecutionRequirement(
                        "caller_state_dependency",
                        "balanceOf(msg.sender) > 0",
                        f"{producer.name}:erc4626-balance",
                        "unresolved",
                        "standard ERC-4626 positive-withdraw path requires a non-zero caller share balance and no compiler-backed constructible writer for that caller state was discovered",
                    )
                )
        if producer_reads:
            for state in producer_reads:
                requirements.append(
                    ExecutionRequirement(
                        "execution_state_dependency",
                        f"{producer.name} -> {state}",
                        f"{producer.name}:compiler-state",
                        "discovered",
                        "compiler-backed state read used by the value producer; a constructible "
                        "prerequisite must be identified and verified before reachability is treated as satisfied",
                    )
                )

    return tuple(dict.fromkeys(requirements))


def _is_experiment_constraint(contract: ContractModel, function: FunctionModel, predicate: str) -> bool:
    """Separate pure input/local path conditions from environment prerequisites.

    Predicates over ABI inputs, pure local derivations, literals, and source
    constants are constraints for the generated experiment. Persistent state,
    ambient context, and call-derived locals remain blocking prerequisites.
    """
    identifiers = set(re.findall(r"\b[A-Za-z_]\w*\b", predicate))
    state_names = set(contract.state_variables)
    parameter_names = {parameter.name for parameter in function.parameters if parameter.name}
    local_names = {name for name, _ in function.execution_value_bindings}
    ambient = {"msg", "tx", "block", "now"}
    # A one-sided numeric comparison between an ABI input and modeled state
    # can be satisfied by a conservative extremal input (for example
    # epoch >= depositEpoch -> max uint). It is an experiment input constraint,
    # not an environmental prerequisite, provided no ambient/call-derived value
    # participates in the predicate.
    parameter_state_order = bool(
        identifiers & parameter_names
        and identifiers & state_names
        and re.search(r"(?:>=|<=|>|<)", predicate)
        and not re.search(r"\\b(?:msg|tx|block|now)\\b", predicate)
    )
    if parameter_state_order:
        return True

    if identifiers & state_names or identifiers & ambient or "$." in predicate:
        return False
    bound_names = parameter_names | local_names

    if not (identifiers & bound_names):
        # A repeated lower-case identifier across multiple path predicates is
        # commonly a local derived scalar whose declaration the lightweight
        # parser could not bind. Repetition is weak evidence, so only use it
        # for the experiment-constraint classification; state/ambient names
        # were already rejected above.
        predicate_frequency = {
            name: sum(1 for item in function.execution_predicates if re.search(
                rf"\b{re.escape(name)}\b", item
            ))
            for name in identifiers
        }
        repeated_local = any(
            frequency >= 2 and name[:1].islower()
            for name, frequency in predicate_frequency.items()
        )
        if not repeated_local:
            # An unresolved identifier with no ABI/local binding is not assumed
            # to be a harmless constant; keep the gate fail-closed.
            return False
    call_bound_locals = {
        name
        for name, expression in function.execution_value_bindings
        if re.search(r"\b[A-Za-z_]\w*\s*\(", expression)
    }
    if identifiers & call_bound_locals:
        return False
    return True


def _execution_requirements(
    contract: ContractModel,
    function: FunctionModel,
) -> tuple[ExecutionRequirement, ...]:
    polarities = dict(function.execution_predicate_polarities)
    requirements: list[ExecutionRequirement] = []
    for predicate in function.execution_predicates:
        polarity = polarities.get(predicate, "unknown")
        detail = {
            "must_hold": "execution predicate must hold for the normal security-relevant path",
            "must_not_hold": "execution predicate is a guarded revert condition and must not hold",
            "unknown": "execution predicate polarity could not be established statically",
        }.get(polarity, "execution predicate polarity is unknown")
        status = "constraint" if _is_experiment_constraint(contract, function, predicate) else "required"
        if status == "constraint":
            detail = (
                "pure input/local execution constraint; the generated experiment "
                "must satisfy it before the security-relevant assertion"
            )
        requirements.append(
            ExecutionRequirement(
                "execution_predicate",
                predicate,
                f"{function.name}:body",
                status,
                detail,
            )
        )
    return tuple(requirements)


def _state_requirements(function: FunctionModel) -> tuple[ExecutionRequirement, ...]:
    polarities = dict(function.state_predicate_polarities)
    return tuple(
        ExecutionRequirement(
            "state_predicate",
            predicate,
            f"{function.name}:body",
            "required",
            {
                "must_hold": "state predicate must hold for the normal execution path",
                "must_not_hold": "state predicate is a guarded revert condition and must not hold",
                "unknown": "state predicate polarity could not be established statically",
            }.get(polarities.get(predicate, "unknown"), "state predicate polarity is unknown"),
        )
        for predicate in function.state_predicates
    )


def _constraint_state_requirements(
    function: FunctionModel,
    constraints: tuple[ConstraintEvidence, ...],
) -> tuple[ExecutionRequirement, ...]:
    requirements: list[ExecutionRequirement] = []
    for constraint in constraints:
        if constraint.function != function.name:
            continue
        if ".length" in constraint.predicate:
            requirements.append(
                ExecutionRequirement(
                    "state_predicate",
                    constraint.predicate,
                    f"{function.name}:compiler-constraint",
                    "required",
                    "compiler-linked collection bound requires sufficient initialized state",
                )
            )
    return tuple(requirements)


def _state_names_from_predicates(function: FunctionModel) -> tuple[str, ...]:
    names: list[str] = []
    polarities = dict(function.state_predicate_polarities)
    for predicate in function.state_predicates:
        polarity = polarities.get(predicate)
        # A positive requirement directly names the state. A reverting guard
        # such as items.length == 0 also implies a positive setup requirement:
        # the normal path needs a non-empty collection. Other negative/unknown
        # predicates remain conservative and do not invent a setup transition.
        positive_collection_requirement = bool(
            re.search(r"\b[A-Za-z_]\w*\.length\s*(?:>|>=)\s*(?:0|1)\b", predicate)
        )
        if polarity == "must_not_hold":
            if not re.search(r"\b[A-Za-z_]\w*\.length\s*==\s*0\b", predicate):
                continue
        elif polarity == "unknown":
            if not positive_collection_requirement:
                continue
        for match in re.finditer(r"\b([A-Za-z_]\w*)(?:\.length)?\b", predicate):
            name = match.group(1)
            if name in {"true", "false", "address", "bytes", "uint", "int"}:
                continue
            if name not in names:
                names.append(name)
    return tuple(names)

def _state_setup_candidates(
    contract: ContractModel,
    function: FunctionModel,
    constraints: tuple[ConstraintEvidence, ...] = (),
    semantic_evidence: tuple[SemanticRelationshipEvidence, ...] = (),
) -> tuple[ExecutionRequirement, ...]:
    """Identify generic writer functions that may establish required state.

    This is a planning surface, not proof that the writer can satisfy the
    predicate. A candidate is constructible only when its ABI is composed of
    primitive values; guarded writers remain usable through the generic caller
    role model.
    """
    state_names = set(_state_names_from_predicates(function))
    for constraint in constraints:
        if constraint.function != function.name or ".length" not in constraint.predicate:
            continue
        match = re.search(r"\b([A-Za-z_]\w*)\.length\b", constraint.predicate)
        if match:
            state_names.add(match.group(1))
    if not state_names:
        return ()

    semantic_effects = build_state_effect_index(semantic_evidence)
    candidates: list[ExecutionRequirement] = []
    for state in state_names:
        for writer in contract.functions:
            if writer.name == function.name or writer.visibility not in {"public", "external"}:
                continue
            semantic_writes = state_writes_for_function(semantic_effects, writer.name)
            touched = state in writer.writes or (semantic_writes is not None and state in semantic_writes) or any(
                receiver == state and method in {"push", "pop"}
                for receiver, method in writer.external_calls
            )
            if not touched:
                continue
            primitive_abi = all(
                parameter.type.strip().split()[0].rstrip("[]") in {"address", "bool", "string", "bytes"}
                or parameter.type.strip().split()[0].rstrip("[]").startswith(("uint", "int", "bytes"))
                for parameter in writer.parameters
            )
            runtime_dependencies = tuple(
                requirement
                for requirement in _runtime_requirements(contract, writer)
                if requirement.subject.split(".")[-1] not in {"push", "pop"}
            )
            status = "constructible" if primitive_abi and not runtime_dependencies else "unresolved"
            if not primitive_abi:
                detail = f"candidate transition {writer.name} has non-primitive parameters and cannot be synthesized generically"
            elif runtime_dependencies:
                detail = (
                    f"candidate transition {writer.name} touches modeled prerequisite state {state} "
                    "but has unresolved runtime dependencies"
                )
            else:
                detail = f"candidate transition that touches modeled prerequisite state {state}"
            candidates.append(
                ExecutionRequirement(
                    "state_setup_candidate",
                    writer.name,
                    f"{function.name}:state:{state}",
                    status,
                    detail,
                )
            )
    return tuple(dict.fromkeys(candidates))


def constructible_state_setup_plan(
    contract: ContractModel,
    function: FunctionModel,
    constraints: tuple[ConstraintEvidence, ...] = (),
    semantic_evidence: tuple[SemanticRelationshipEvidence, ...] = (),
    *,
    max_depth: int = 8,
) -> tuple[SetupAction, ...]:
    """Resolve state setup recursively and fail closed on unsatisfied prerequisites."""
    functions = tuple(dict.fromkeys((*contract.functions, *contract.inherited_functions)))
    effects = build_state_effect_index(semantic_evidence)
    memo: dict[tuple[str, tuple[str, ...]], tuple[SetupAction, ...] | None] = {}

    def writers_for(state: str) -> tuple[FunctionModel, ...]:
        result = []
        for candidate in functions:
            if candidate.visibility not in {"public", "external"}:
                continue
            semantic_writes = state_writes_for_function(effects, candidate.name)
            touched = state in candidate.writes or (semantic_writes is not None and state in semantic_writes) or any(
                receiver == state and method in {"push", "pop"} for receiver, method in candidate.external_calls
            )
            if touched:
                result.append(candidate)
        return tuple(result)

    def required_state_names(fn: FunctionModel) -> tuple[str, ...]:
        names = list(_state_names_from_predicates(fn))
        for constraint in constraints:
            if constraint.function != fn.name or ".length" not in constraint.predicate:
                continue
            match = re.search(r"\b([A-Za-z_]\w*)\.length\b", constraint.predicate)
            if match and match.group(1) not in names:
                names.append(match.group(1))

        # Execution-readiness dependencies can introduce state that is not
        # mentioned in the consumer's own state-predicate list. For example,
        # a positive maxWithdraw(msg.sender) path requires the caller to own
        # shares. Feed those discovered state dependencies into the same
        # recursive writer solver used for ordinary state predicates.
        readiness = inspect_execution_readiness(contract, fn, constraints, semantic_evidence)
        for requirement in readiness.execution_requirements:
            if requirement.kind != "caller_state_dependency" or requirement.status != "discovered":
                continue
            match = re.search(r"\bbalanceOf\s*\(", requirement.subject)
            if match and "balanceOf" not in names:
                names.append("balanceOf")
        return tuple(names)

    def visit(fn: FunctionModel, stack: tuple[str, ...], depth: int) -> tuple[SetupAction, ...] | None:
        key = (fn.name, stack)
        if key in memo:
            return memo[key]
        if depth > max_depth or fn.name in stack:
            memo[key] = None
            return None
        readiness = inspect_execution_readiness(contract, fn, constraints, semantic_evidence)
        if any(item.status == "unresolved" for item in readiness.blockers):
            memo[key] = None
            return None
        if any(item.kind == "caller_state_dependency" and item.status == "unresolved" for item in readiness.execution_requirements):
            memo[key] = None
            return None
        if any(item.status == "unresolved" for item in readiness.runtime_requirements):
            memo[key] = None
            return None
        if any(
            item.kind in {"execution_value_dependency", "execution_value_runtime_dependency"}
            and item.status == "unresolved"
            for item in readiness.execution_requirements
        ):
            memo[key] = None
            return None
        if any(item.kind == "execution_predicate" and "polarity could not be established" in item.detail for item in readiness.execution_requirements):
            memo[key] = None
            return None
        actions = []
        for state in required_state_names(fn):
            selected = None
            for writer in writers_for(state):
                if writer.name in stack or writer.name == fn.name:
                    continue
                primitive = all(
                    parameter.type.strip().split()[0].rstrip("[]") in {"address", "bool", "string", "bytes"}
                    or parameter.type.strip().split()[0].rstrip("[]").startswith(("uint", "int", "bytes"))
                    for parameter in writer.parameters
                )
                if not primitive:
                    continue
                nested = visit(writer, (*stack, fn.name), depth + 1)
                if nested is not None:
                    selected = (*nested, SetupAction(writer.name, caller_role(writer), (*stack, fn.name, state)))
                    break
            if selected is None:
                memo[key] = None
                return None
            seen = {item.function for item in actions}
            actions.extend(item for item in selected if item.function not in seen)
        memo[key] = tuple(actions)
        return memo[key]

    return visit(function, (), 0) or ()


def inspect_execution_readiness(
    contract: ContractModel,
    function: FunctionModel | None = None,
    constraints: tuple[ConstraintEvidence, ...] = (),
    semantic_evidence: tuple[SemanticRelationshipEvidence, ...] = (),
) -> ExecutionReadiness:
    """Derive target execution prerequisites without making vulnerability claims."""
    selected = function
    return ExecutionReadiness(
        contract=contract.name,
        constructor_requirements=_constructor_requirements(contract),
        caller_requirements=_caller_requirements(selected) if selected else (),
        runtime_requirements=_runtime_requirements(contract, selected) if selected else (),
        execution_requirements=(
            (*_execution_requirements(contract, selected), *_execution_dataflow_requirements(contract, selected, semantic_evidence))
            if selected else ()
        ),
        state_requirements=(
            (*_state_requirements(selected), *_constraint_state_requirements(selected, constraints))
            if selected else ()
        ),
        state_setup_candidates=_state_setup_candidates(contract, selected, constraints, semantic_evidence) if selected else (),
    )
