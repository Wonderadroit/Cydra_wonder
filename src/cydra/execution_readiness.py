from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .compiler_constraints import ConstraintEvidence
from .interface_resolver import resolve_named_type_source
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


def _constructor_requirements(contract: ContractModel) -> tuple[ExecutionRequirement, ...]:
    if contract.constructor is None:
        return ()

    requirements: list[ExecutionRequirement] = []
    for parameter in contract.constructor.parameters:
        base = parameter.type.strip().split()[0].rstrip("[]")
        primitive = base in {"address", "bool", "string", "bytes"} or base.startswith(
            ("uint", "int", "bytes")
        )
        if not primitive:
            requirements.append(
                ExecutionRequirement(
                    "constructor_dependency",
                    base,
                    "constructor",
                    "required",
                    f"constructor parameter {parameter.name or '<unnamed>'} uses a contract/interface/custom type",
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
                        "required",
                        "address parameter is a likely role/dependency binding by declared parameter name",
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
    except (FileNotFoundError, ValueError, OSError, UnicodeError):
        return False
    resolved_path = Path(resolved)
    if not resolved_path.is_absolute():
        resolved_path = (project_root / resolved_path).resolve()
    try:
        source = resolved_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return False
    return bool(re.search(r"\\blibrary\\s+" + re.escape(receiver) + r"\\b", source))

def _runtime_requirements(contract: ContractModel, function: FunctionModel) -> tuple[ExecutionRequirement, ...]:
    requirements: list[ExecutionRequirement] = []
    for receiver, method in function.external_calls:
        if _runtime_receiver_is_library(contract, receiver):
            continue
        requirements.append(
            ExecutionRequirement(
                "runtime_dependency",
                f"{receiver}.{method}",
                f"{function.name}:external_call",
                "required",
                "function performs an external call whose target/state may be required for execution",
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

        requirements.append(
            ExecutionRequirement(
                "execution_dataflow",
                f"{local} <- {expression}",
                f"{function.name}:body",
                "required",
                "execution predicate depends on a locally bound call/input value; "
                "the binding must be resolved before reachability is treated as satisfied",
            )
        )

        call_match = re.match(r"^(?:[A-Za-z_]\w*\.)?(?P<name>[A-Za-z_]\w*)\s*\(", expression)
        if not call_match:
            continue
        producer_name = call_match.group("name")
        producer = functions_by_name.get(producer_name)
        if producer is None:
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


def _execution_requirements(function: FunctionModel) -> tuple[ExecutionRequirement, ...]:
    polarities = dict(function.execution_predicate_polarities)
    return tuple(
        ExecutionRequirement(
            "execution_predicate",
            predicate,
            f"{function.name}:body",
            "required",
            {
                "must_hold": "execution predicate must hold for the normal security-relevant path",
                "must_not_hold": "execution predicate is a guarded revert condition and must not hold",
                "unknown": "execution predicate polarity could not be established statically",
            }.get(polarities.get(predicate, "unknown"), "execution predicate polarity is unknown"),
        )
        for predicate in function.execution_predicates
    )


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
        if polarity not in {None, "must_hold"}:
            if not (
                positive_collection_requirement
                or (
                    polarity == "must_not_hold"
                    and re.search(r"\b[A-Za-z_]\w*\.length\s*==\s*0\b", predicate)
                )
            ):
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
            (*_execution_requirements(selected), *_execution_dataflow_requirements(contract, selected, semantic_evidence))
            if selected else ()
        ),
        state_requirements=(
            (*_state_requirements(selected), *_constraint_state_requirements(selected, constraints))
            if selected else ()
        ),
        state_setup_candidates=_state_setup_candidates(contract, selected, constraints, semantic_evidence) if selected else (),
    )
