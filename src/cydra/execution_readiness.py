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

    @property
    def blockers(self) -> tuple[ExecutionRequirement, ...]:
        return tuple(
            item
            for item in (
                *self.constructor_requirements,
                *self.caller_requirements,
                *self.runtime_requirements,
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
    return tuple(
        ExecutionRequirement(
            "state_predicate",
            predicate,
            f"{function.name}:body",
            "required",
            "function contains a predicate over modeled target state",
        )
        for predicate in function.state_predicates
    )


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
    )
