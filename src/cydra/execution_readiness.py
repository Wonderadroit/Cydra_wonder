from __future__ import annotations

from dataclasses import dataclass
import re

from .models import ContractModel, FunctionModel


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

    @property
    def blockers(self) -> tuple[ExecutionRequirement, ...]:
        return tuple(
            item
            for item in (
                *self.constructor_requirements,
                *self.caller_requirements,
                *self.runtime_requirements,
                *self.state_requirements,
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


def _runtime_requirements(function: FunctionModel) -> tuple[ExecutionRequirement, ...]:
    return tuple(
        ExecutionRequirement(
            "runtime_dependency",
            f"{receiver}.{method}",
            f"{function.name}:external_call",
            "required",
            "function performs an external call whose target/state may be required for execution",
        )
        for receiver, method in function.external_calls
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


def _state_names_from_predicates(function: FunctionModel) -> tuple[str, ...]:
    names: list[str] = []
    polarities = dict(function.state_predicate_polarities)
    for predicate in function.state_predicates:
        if polarities.get(predicate) != "must_hold":
            continue
        for name in re.findall(r"\b[A-Za-z_]\w*\b", predicate):
            if name in {"true", "false", "address", "bytes", "uint", "int"}:
                continue
            if name not in names:
                names.append(name)
    return tuple(names)


def _state_setup_candidates(
    contract: ContractModel,
    function: FunctionModel,
) -> tuple[ExecutionRequirement, ...]:
    """Identify generic writer functions that may establish required state.

    This is a planning surface, not proof that the writer can satisfy the
    predicate. A candidate is constructible only when its ABI is composed of
    primitive values; guarded writers remain usable through the generic caller
    role model.
    """
    state_names = _state_names_from_predicates(function)
    if not state_names:
        return ()

    candidates: list[ExecutionRequirement] = []
    for state in state_names:
        for writer in contract.functions:
            if writer.name == function.name or writer.visibility not in {"public", "external"}:
                continue
            touched = state in writer.writes or any(
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
            status = "constructible" if primitive_abi else "unresolved"
            candidates.append(
                ExecutionRequirement(
                    "state_setup_candidate",
                    writer.name,
                    f"{function.name}:state:{state}",
                    status,
                    f"candidate transition that touches modeled prerequisite state {state}",
                )
            )
    return tuple(dict.fromkeys(candidates))


def inspect_execution_readiness(
    contract: ContractModel,
    function: FunctionModel | None = None,
) -> ExecutionReadiness:
    """Derive target execution prerequisites without making vulnerability claims."""
    selected = function
    return ExecutionReadiness(
        contract=contract.name,
        constructor_requirements=_constructor_requirements(contract),
        caller_requirements=_caller_requirements(selected) if selected else (),
        runtime_requirements=_runtime_requirements(selected) if selected else (),
        state_requirements=_state_requirements(selected) if selected else (),
        state_setup_candidates=_state_setup_candidates(contract, selected) if selected else (),
    )
