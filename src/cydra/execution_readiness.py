from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .compiler_constraints import ConstraintEvidence
from .interface_resolver import resolve_interface, resolve_named_type_source, resolve_import, _imports_for, _strip_comments
from .models import ContractModel, FunctionModel
from .ast_dataflow import SemanticRelationshipEvidence
from .semantic_state_effects import build_state_effect_index, state_reads_for_function, state_writes_for_function
from .namespaced_state_observation import plan_namespaced_state_observation
from .solidity_model import parse_solidity, _resolve_inherited_contract_source


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
    category: str = "unknown"


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

_SOLIDITY_BUILTIN_FUNCTIONS = {
    "abi.decode", "abi.encode", "abi.encodePacked", "abi.encodeWithSelector",
    "abi.encodeWithSignature", "abi.encodeCall", "bytes.concat", "string.concat",
    "addmod", "mulmod", "keccak256", "sha256", "ripemd160", "ecrecover",
}
_SOLIDITY_CAST_RE = re.compile(
    r"^(?:address(?:\s+payable)?|bool|string|bytes(?:\d+)?|u?int(?:\d+)?|fixed(?:\d+x\d+)?|ufixed(?:\d+x\d+)?)$"
)


def _is_deterministic_expression(expression: str) -> bool:
    """Return True when all call-shaped operations are Solidity-local builtins/casts.

    Type conversions and ABI/hash arithmetic helpers do not introduce a runtime
    contract dependency. User-defined/internal calls remain producer dependencies.
    """
    calls = re.findall(r"\b([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?)\s*\(", expression)
    for call in calls:
        if call in _SOLIDITY_BUILTIN_FUNCTIONS:
            continue
        if _SOLIDITY_CAST_RE.fullmatch(call):
            continue
        return False
    return True


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
            if any((parent / marker_name).exists() for marker_name in ("foundry.toml", "package.json", "remappings.txt"))
        ),
        source_path.parent,
    )

    def resolves_to_interface(type_name: str) -> bool:
        try:
            if "." in type_name:
                namespace, member = type_name.split(".", 1)
                resolved = resolve_interface(project_root, source_path, namespace)
                return member in resolved.declared_types
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


def _caller_principal_from_predicate(predicate: str) -> str | None:
    """Extract a principal from a direct caller-to-identifier equality."""
    caller = r"(?:msg\.sender|_msgSender\(\))"
    identifier = r"[A-Za-z_]\w*"
    for pattern in (
        rf"^\s*{caller}\s*==\s*(?P<principal>{identifier})\s*$",
        rf"^\s*(?P<principal>{identifier})\s*==\s*{caller}\s*$",
    ):
        match = re.match(pattern, predicate.strip())
        if match:
            return match.group("principal")
    return None


def _predicate_role(predicate: str) -> str | None:
    principal = _caller_principal_from_predicate(predicate)
    return _address_role(principal) if principal else None


def _balanced_function_body(source: str, opening: int) -> str:
    """Return a brace-balanced Solidity function body from its opening brace."""
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[opening + 1:index]
    return source[opening + 1:]


def _function_body_from_source(contract: ContractModel, function: FunctionModel) -> str | None:
    """Resolve a modeled function body through the bounded target inheritance graph."""
    source_path = Path(contract.source).resolve()
    root = next(
        (parent for parent in (source_path.parent, *source_path.parents)
         if any((parent / marker).exists() for marker in ("foundry.toml", "package.json", "remappings.txt"))),
        source_path.parent,
    )
    visited: set[Path] = set()

    def walk(path: Path, inherits: tuple[str, ...]) -> str | None:
        path = path.resolve()
        if path in visited or not path.is_file():
            return None
        visited.add(path)
        try:
            source = _strip_comments(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError):
            return None
        match = re.search(rf"\bfunction\s+{re.escape(function.name)}\s*\(", source)
        if match:
            opening = source.find("{", match.end())
            if opening >= 0:
                return _balanced_function_body(source, opening)
        for inherited in inherits:
            try:
                resolved = _resolve_inherited_contract_source(root, path, inherited)
            except (OSError, UnicodeError):
                continue
            if resolved is None:
                continue
            try:
                bases = parse_solidity(resolved, include_inherited=False)
            except (OSError, UnicodeError):
                bases = ()
            base = next((item for item in bases if item.name == inherited), None)
            result = walk(resolved, base.inherits if base else ())
            if result is not None:
                return result
        return None

    return walk(source_path, contract.inherits)


def _state_principal_from_predicate(predicate: str) -> str | None:
    """Extract a bare state identifier used as the caller principal."""
    caller = r"(?:msg\.sender|_msgSender\(\))"
    identifier = r"[A-Za-z_]\w*"
    for pattern in (
        rf"^\s*{caller}\s*==\s*(?P<principal>{identifier})\s*$",
        rf"^\s*(?P<principal>{identifier})\s*==\s*{caller}\s*$",
    ):
        match = re.match(pattern, predicate.strip())
        if match:
            return match.group("principal")
    return None


def _state_principal_caller_role(function: FunctionModel, contract: ContractModel) -> str | None:
    """Resolve caller role through a direct state <- caller initializer."""
    principals = tuple(
        name for name in (
            _state_principal_from_predicate(predicate)
            for predicate in function.authorization_predicates
        )
        if name
    )
    if not principals:
        return None
    principal = principals[0]
    functions = tuple(dict.fromkeys(item for item in (*contract.functions, *contract.inherited_functions) if item is not None))
    for writer in functions:
        body = _function_body_from_source(contract, writer)
        if body and re.search(
            rf"\b{re.escape(principal)}\s*=\s*(?:msg\.sender|_msgSender\(\))\s*;",
            body,
        ):
            return caller_role(writer, contract)
    return None


def _caller_state_principal_provenance(
    contract: ContractModel | None,
    principal: str | None,
) -> tuple[str, ...]:
    """Return source-backed provenance for a caller principal stored in state."""
    if contract is None or principal is None:
        return ()
    functions = tuple(dict.fromkeys((*contract.functions, *contract.inherited_functions)))
    for writer in functions:
        body = _function_body_from_source(contract, writer)
        if not body:
            continue
        if not re.search(
            rf"\b{re.escape(principal)}\s*=\s*(?:msg\.sender|_msgSender\(\))\s*;",
            body,
        ):
            continue
        role = caller_role(writer, contract)
        if role:
            return (f"caller_via:{writer.name}", f"writer_role:{role}")
        return (f"caller_via:{writer.name}", f"writer initializes {principal} from its caller")
    return ()


def caller_role(function: FunctionModel, contract: ContractModel | None = None) -> str | None:
    """Infer a deterministic role binding from source-backed authorization semantics."""
    for modifier in function.modifiers:
        role = _address_role(modifier)
        if role is not None:
            return role
    for predicate in function.authorization_predicates:
        role = _predicate_role(predicate) or _address_role(predicate)
        if role is not None:
            return role
    if contract is not None:
        return _state_principal_caller_role(function, contract)
    return None


def _constructor_role_grants(contract: ContractModel) -> tuple[tuple[str, str], ...]:
    """Collect constructor role grants across the modeled inheritance graph."""
    source_path = Path(contract.source).resolve()
    project_root = next(
        (
            parent
            for parent in (source_path.parent, *source_path.parents)
            if any((parent / marker).exists() for marker in ("foundry.toml", "package.json", "remappings.txt"))
        ),
        source_path.parent,
    )
    grants: list[tuple[str, str]] = []
    visited: set[Path] = set()

    def visit(current: ContractModel) -> None:
        if current.constructor is not None:
            for item in current.constructor.role_grants:
                if item not in grants:
                    grants.append(item)
        current_path = Path(current.source).resolve()
        # OpenZeppelin Ownable establishes the deployment caller as owner even
        # when the dependency source is outside the target checkout's local
        # import graph (for example a remapped lib/ dependency). Treat this as
        # generic library semantics, not target-specific provenance.
        inherited_names = {name.strip().split("(", 1)[0] for name in current.inherits}
        if {"Ownable", "Ownable2Step"} & inherited_names and ("owner", "msg.sender") not in grants:
            grants.append(("owner", "msg.sender"))
        for inherited_name in current.inherits:
            try:
                resolved_path = _resolve_inherited_contract_source(project_root, current_path, inherited_name)
            except (OSError, UnicodeError):
                continue
            if resolved_path is None:
                continue
            if resolved_path in visited:
                continue
            visited.add(resolved_path)
            try:
                bases = parse_solidity(resolved_path, include_inherited=False)
            except (OSError, UnicodeError):
                continue
            base = next((item for item in bases if item.name == inherited_name), None)
            if base is not None:
                visit(base)

    visit(contract)
    return tuple(grants)


def _authorization_predicates_from_body(body: str) -> tuple[str, ...]:
    """Extract direct caller predicates from a modifier body conservatively."""
    predicates: list[str] = []
    for match in re.finditer(r"\brequire\s*\(", body):
        opening = body.find("(", match.start())
        depth = 0
        for index in range(opening, len(body)):
            if body[index] == "(":
                depth += 1
            elif body[index] == ")":
                depth -= 1
                if depth == 0:
                    predicate = body[opening + 1:index].split(",", 1)[0].strip()
                    if "msg.sender" in predicate or "_msgSender()" in predicate:
                        predicates.append(predicate)
                    break
    return tuple(dict.fromkeys(predicates))


def _caller_requirements(
    function: FunctionModel,
    contract: ContractModel | None = None,
) -> tuple[ExecutionRequirement, ...]:
    requirements: list[ExecutionRequirement] = []
    modifier_map = {
        item.name: item
        for item in (
            (*contract.modifiers, *contract.inherited_modifiers)
            if contract is not None
            else ()
        )
    }
    invocations = dict(function.modifier_invocations)

    for modifier in function.modifiers:
        # Lifecycle and reentrancy modifiers do not establish caller identity.
        if modifier in {"initializer", "reinitializer", "onlyInitializing", "nonReentrant", "nonReentrantView"}:
            continue
        if modifier.startswith(("returns", "override")):
            continue

        invocation_args = invocations.get(modifier, ())
        definition = modifier_map.get(modifier)
        # OpenZeppelin's onlyOwner is stable library semantics. Its source may
        # be outside the bounded target import graph, so recognize the modifier
        # name itself rather than treating the missing dependency source as an
        # authorization mystery.
        known_library_caller_modifier = modifier in {"onlyOwner", "onlyOwner2Step"}
        if definition is not None or known_library_caller_modifier:
            caller_tokens = ("msg.sender", "_msgSender()", "tx.origin")
            role_tokens = ("hasRole(", "_checkRole(", "onlyRole", "role")
            # A known library modifier may be intentionally represented without
            # its source definition in the bounded target model. Treat the
            # modifier's documented semantics as sufficient evidence, while
            # keeping unresolved definitions safe for ordinary modifiers.
            definition_body = definition.body if definition is not None else ""
            has_caller_check = known_library_caller_modifier or any(
                token in definition_body for token in caller_tokens
            )
            has_role_check = any(token in definition_body for token in role_tokens)
            if has_caller_check or has_role_check:
                rendered_args = ", ".join(invocation_args)
                # Map common modifier semantics to the role they establish.
                # onlyOwner is an owner check; role-bearing modifiers expose
                # their role through the invocation argument. Keep this generic
                # so constructor provenance can satisfy either form.
                required_role = (
                    "owner"
                    if modifier in {"onlyOwner", "onlyOwner2Step"}
                    else (invocation_args[0] if invocation_args else None)
                )
                owner_grants = _constructor_role_grants(contract)
                role_established_for_deployer = bool(
                    required_role
                    and any(
                        granted_role == required_role
                        and account in {"msg.sender", "_msgSender()"}
                        for granted_role, account in owner_grants
                    )
                )
                constructor_params = (
                    contract.constructor.parameters if contract.constructor is not None else ()
                )
                owner_established_for_deployer = bool(
                    required_role == "owner"
                    and any(
                        granted_role == "owner"
                        and (
                            account in {"msg.sender", "_msgSender()"}
                            or any(
                                account == parameter.name
                                and _address_role(parameter.name or "")
                                for parameter in constructor_params
                            )
                        )
                        for granted_role, account in owner_grants
                    )
                )
                if role_established_for_deployer or owner_established_for_deployer:
                    requirements.append(
                        ExecutionRequirement(
                            "caller_role",
                            f"{modifier}({rendered_args})",
                            f"{function.name}:modifier",
                            "constraint",
                            "target constructor establishes the invoked role for its deployment caller; "
                            "state setup is executed by that same deployment caller",
                        )
                    )
                    continue
                predicate_roles = tuple(
                    role
                    for role in (
                        _predicate_role(predicate)
                        for predicate in _authorization_predicates_from_body(definition_body)
                    )
                    if role is not None
                )
                inferred_role = predicate_roles[0] if len(set(predicate_roles)) == 1 else None
                if inferred_role is not None:
                    owner_grants = _constructor_role_grants(contract)
                    if any(
                        granted_role == inferred_role
                        and account in {"msg.sender", "_msgSender()"}
                        for granted_role, account in owner_grants
                    ):
                        requirements.append(
                            ExecutionRequirement(
                                "caller_role",
                                f"{modifier}({rendered_args})",
                                f"{function.name}:modifier",
                                "constraint",
                                "modifier source directly compares the caller with a role principal "
                                "whose constructor provenance binds that role to the deployment caller",
                            )
                        )
                        continue
                modifier_state_principals = tuple(
                    dict.fromkeys(
                        principal
                        for predicate in _authorization_predicates_from_body(definition_body)
                        for principal in [_caller_principal_from_predicate(predicate)]
                        if principal is not None
                    )
                )
                modifier_state_provenance = tuple(
                    principal
                    for principal in modifier_state_principals
                    if _caller_state_principal_provenance(contract, principal)
                ) if contract is not None else ()
                if modifier_state_provenance:
                    principal = modifier_state_provenance[0]
                    requirements.append(
                        ExecutionRequirement(
                            "caller_state_principal",
                            principal,
                            f"{function.name}:modifier",
                            "constraint",
                            "modifier caller check is source-backed by a deterministic state principal; "
                            + ", ".join(_caller_state_principal_provenance(contract, principal))
                            + "; sequence planning may establish the principal before the protected call",
                            category="caller",
                        )
                    )
                    continue

                detail = (
                    f"resolved modifier body establishes caller authorization semantics"
                    f"{': invocation arguments ' + rendered_args if rendered_args else ''}; "
                    "the required identity/role must still be established from target state or "
                    "a legitimate role-establishment transition"
                )
            else:
                detail = (
                    "resolved modifier definition does not expose a recognized caller/role "
                    "predicate; authorization remains unresolved"
                )
        else:
            detail = (
                "function signature declares a custom modifier whose definition could not be "
                "resolved through the target import/inheritance graph"
            )

        requirements.append(
            ExecutionRequirement(
                "caller_role",
                f"{modifier}({', '.join(invocation_args)})" if invocation_args else modifier,
                f"{function.name}:modifier",
                "required",
                detail,
            )
        )

    for predicate in function.authorization_predicates:
        principal = _caller_principal_from_predicate(predicate)
        provenance = (
            _caller_state_principal_provenance(contract, principal)
            if contract is not None and principal is not None
            else ()
        )
        if provenance:
            requirements.append(
                ExecutionRequirement(
                    "caller_state_principal",
                    principal,
                    f"{function.name}:body",
                    "constraint",
                    "caller identity is source-backed by a deterministic state principal; "
                    + ", ".join(provenance)
                    + "; sequence planning may establish the principal before the protected call",
                    category="caller",
                )
            )
        else:
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


def runtime_dependency_constructor_bindings(
    contract_model: ContractModel,
    function: FunctionModel,
    receiver_name: str | None = None,
) -> tuple[tuple[str, object], ...]:
    """Resolve state-backed external receivers that can be materialized generically."""
    source_path = Path(contract_model.source).resolve()
    root = next(
        (
            parent for parent in (source_path.parent, *source_path.parents)
            if any((parent / marker).exists() for marker in ("foundry.toml", "package.json", "remappings.txt"))
        ),
        source_path.parent,
    )
    constructor_parameters = {
        parameter.name
        for parameter in (contract_model.constructor.parameters if contract_model.constructor else ())
        if parameter.name
    }
    if not constructor_parameters:
        return ()
    queue = [source_path]
    visited: set[Path] = set()
    sources: list[Path] = []
    while queue:
        path = queue.pop().resolve()
        if path in visited or not path.is_file():
            continue
        visited.add(path)
        sources.append(path)
        try:
            imports = _imports_for(path)
        except (OSError, UnicodeError):
            continue
        for import_path in imports:
            resolved = resolve_import(root, path, import_path)
            if resolved is None:
                direct = (path.parent / import_path).resolve()
                if direct.is_file():
                    resolved = (direct, "declared_import")
            if resolved is not None:
                queue.append(resolved[0])
    runtime_receivers: set[str] = set()
    for call in function.external_calls:
        if isinstance(call, (tuple, list)):
            receiver = str(call[0]) if call else ""
        else:
            raw_call = str(call)
            receiver = raw_call.rsplit(".", 1)[0] if "." in raw_call else raw_call
        if receiver not in {"abi", "block", "msg", "tx", "type", "super"} and (
            receiver_name is None or receiver == receiver_name
        ):
            runtime_receivers.add(receiver)
    bindings: list[tuple[str, object]] = []
    for receiver in sorted(runtime_receivers):
        declaration = re.compile(
            rf"\b(?P<type>[A-Za-z_]\w*)\s+"
            rf"(?:(?:public|private|internal|external|immutable|constant)\s+)*"
            rf"{re.escape(receiver)}\s*;"
        )
        for path in sources:
            try:
                source = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            match = declaration.search(source)
            if not match:
                continue
            interface_name = match.group("type")
            assignment = re.search(
                rf"\b{re.escape(receiver)}\s*=\s*{re.escape(interface_name)}\s*\(\s*(?P<parameter>[A-Za-z_]\w*)\s*\)",
                source,
            )
            if assignment is None:
                # Constructor parameters are frequently assigned directly to
                # interface-typed state without an explicit interface cast.
                # The declared receiver type already supplies the interface
                # provenance, so recover this form without guessing a target.
                assignment = re.search(
                    rf"\b{re.escape(receiver)}\s*=\s*(?P<parameter>[A-Za-z_]\w*)\s*;",
                    source,
                )
            if assignment is None or assignment.group("parameter") not in constructor_parameters:
                continue
            try:
                resolved = resolve_interface(root, path, interface_name)
            except (FileNotFoundError, ValueError, OSError, UnicodeError):
                continue
            item = (assignment.group("parameter"), resolved)
            if item not in bindings:
                bindings.append(item)
            break
    return tuple(bindings)

def _runtime_requirements(contract: ContractModel, function: FunctionModel) -> tuple[ExecutionRequirement, ...]:
    requirements: list[ExecutionRequirement] = []
    state_names = set(contract.state_variables)
    parameter_names = {
        parameter.name
        for parameter in function.parameters
        if parameter.name
    }
    bound_local_names = {
        name for name, _expression in function.execution_value_bindings
    }
    # A returned value that is not a state variable or parameter is evidence of
    # a local value/collection. Member operations on such a value are local
    # execution work, not external runtime targets.
    returned_local_names = {
        match.group(1)
        for expression in function.return_expressions
        for match in [re.match(r"^([A-Za-z_]\w*)\b", expression.strip())]
        if match and match.group(1) not in state_names
    }
    local_value_names = bound_local_names | parameter_names | returned_local_names

    for call in function.external_calls:
        # FunctionModel stores external calls as receiver strings. Older readiness
        # adapters represented them as (receiver, method) pairs; normalize both
        # shapes at this boundary.
        if isinstance(call, (tuple, list)):
            receiver = str(call[0]) if call else ""
            method = str(call[1]) if len(call) > 1 else "*"
        else:
            raw_call = str(call)
            receiver, method = (
                raw_call.rsplit(".", 1) if "." in raw_call else (raw_call, "*")
            )
        # Solidity array mutations are represented by the parser as calls on
        # synthetic receivers, but push/pop are local state operations, not
        # runtime dependencies that need a stubbed external target.
        if method in {"push", "pop"}:
            continue
        if receiver in {"abi", "block", "msg", "tx", "type", "super"}:
            continue
        if receiver in local_value_names and receiver not in state_names:
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
        constructible_binding = bool(
            (configured or configured_cast)
            and runtime_dependency_constructor_bindings(contract, function, receiver)
        )
        status = (
            "constructible"
            if constructible_binding
            else "discovered"
            if configured or configured_cast
            else "required"
        )
        detail = (
            "state-backed external receiver is bound from a constructor interface parameter "
            "and can be materialized by the generic runtime-stub capability"
            if constructible_binding
            else "external call receiver is a modeled contract state value; runtime behavior "
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
    execution_capabilities: frozenset[str] = frozenset(),
) -> tuple[ExecutionRequirement, ...]:
    """Resolve local execution bindings to modeled function producers when possible.

    Discovery of a producer is evidence about program data flow only. It does not
    establish that the producer can return the required value in a live fixture.
    """
    predicates = " ".join(function.execution_predicates)
    requirements: list[ExecutionRequirement] = []
    functions_by_name = {item.name: item for item in (*contract.inherited_functions, *contract.functions) if item is not None}
    semantic_effects = build_state_effect_index(semantic_evidence)

    for local, expression in function.execution_value_bindings:
        if local not in predicates:
            continue

        pure_local_expression = _is_deterministic_expression(expression)
        callback_materialized_call = (
            "callback_state_order_reachability" in execution_capabilities
            and re.search(r"\.\w+\s*\(", expression)
        )
        dataflow_status = "constraint" if pure_local_expression or callback_materialized_call else "required"
        dataflow_detail = (
            "deterministic local derivation used by an experiment constraint; "
            "the generated experiment must reproduce the derivation"
            if pure_local_expression
            else "callback reachability adapter can materialize the discovered external call; "
            "the generated experiment must record the resulting call outcome"
            if callback_materialized_call
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
        # Deterministic Solidity casts/builtins are already classified as local
        # dataflow constraints above. Do not reintroduce them as unresolved
        # call-shaped producer dependencies merely because their syntax contains
        # parentheses.
        if pure_local_expression:
            continue

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
            member_dependency_status = (
                "constraint"
                if callback_materialized_call and member_call.group("method") == "call"
                else "unresolved"
            )
            requirements.append(
                ExecutionRequirement(
                    "execution_value_runtime_dependency",
                    f"{member_call.group('receiver')}.{member_call.group('method')}",
                    f"{function.name}:value-binding",
                    member_dependency_status,
                    (
                        "callback reachability adapter owns the discovered external-call endpoint"
                        if member_dependency_status == "constraint"
                        else "execution value is produced by a non-library member call whose target/state "
                        "must be resolved before the consumer is considered reachable"
                    ),
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
                    "constraint" if callback_materialized_call else "unresolved",
                    (
                        "callback reachability adapter can materialize this discovered external call"
                        if callback_materialized_call
                        else "call-shaped execution value has no compiler/model-resolved local producer; "
                        "the value source must be resolved before reachability is treated as satisfied"
                    ),
                )
            )
            continue

        returns = ", ".join(producer.return_expressions)
        if not returns:
            returns = ", ".join(
                parameter.name or "<unnamed>"
                for parameter in producer.return_parameters
            ) or "<return expression not modeled>"
        producer_postcondition = False
        producer_postcondition_detail = ""
        return_names = {
            parameter.name
            for parameter in producer.return_parameters
            if parameter.name
        }
        producer_polarities = dict(producer.execution_predicate_polarities)
        for return_name in return_names:
            for predicate, polarity in producer_polarities.items():
                if (
                    return_name in re.findall(r"\b[A-Za-z_]\w*\b", predicate)
                    and polarity == "must_not_hold"
                ):
                    producer_postcondition = True
                    producer_postcondition_detail = (
                        f"successful {producer.name} return establishes the named return "
                        f"value {return_name} satisfies its guarded non-revert postcondition"
                    )
                    break
            if producer_postcondition:
                break

        if producer_postcondition and requirements:
            prior = requirements[-1]
            if prior.kind == "execution_dataflow" and prior.subject == f"{local} <- {expression}":
                requirements[-1] = ExecutionRequirement(
                    prior.kind,
                    prior.subject,
                    prior.source,
                    "constraint",
                    producer_postcondition_detail,
                )

        producer_status = "constraint" if producer_postcondition else "discovered"
        producer_detail = (
            producer_postcondition_detail
            if producer_postcondition
            else "modeled local call-result producer; its dependencies and satisfiability "
                 "must be resolved before the consuming path is treated as reachable"
        )
        requirements.append(
            ExecutionRequirement(
                "execution_value_producer",
                f"{local} <- {producer.name}({returns})",
                f"{producer.name}:return",
                producer_status,
                producer_detail,
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
                if candidate is None:
                    continue
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


def _is_experiment_constraint(
    contract: ContractModel,
    function: FunctionModel,
    predicate: str,
    execution_capabilities: frozenset[str] = frozenset(),
) -> bool:
    """Separate pure input/local path conditions from environment prerequisites.

    Predicates over ABI inputs, pure local derivations, literals, and source
    constants are constraints for the generated experiment. Persistent state,
    ambient context, and call-derived locals remain blocking prerequisites.
    """
    identifiers = set(re.findall(r"\b[A-Za-z_]\w*\b", predicate))
    state_names = set(contract.state_variables)
    parameter_names = {parameter.name for parameter in function.parameters if parameter.name}
    local_names = {
        *{name for name, _ in function.execution_value_bindings},
        *(parameter.name for parameter in function.return_parameters if parameter.name),
    }
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
        and not re.search(r"\b(?:msg|tx|block|now)\b", predicate)
    )
    if parameter_state_order:
        return True

    # A calldata value explicitly required to equal the current caller is
    # constructible by the experiment runner: the generated call is made from
    # the attacker/caller identity. This is a semantic input binding, not a
    # target-specific authorization shortcut.
    caller_bound_input = re.search(
        r"\b(?P<path>[A-Za-z_]\w*(?:\.[A-Za-z_]\w+)*)\s*==\s*msg\.sender\b|"
        r"\bmsg\.sender\s*==\s*(?P<reverse>[A-Za-z_]\w*(?:\.[A-Za-z_]\w+)*)\b",
        predicate,
    )
    if caller_bound_input:
        path = caller_bound_input.group("path") or caller_bound_input.group("reverse")
        root = path.split(".", 1)[0]
        if root in parameter_names:
            return True

    # Transaction value is caller-controlled execution input. A predicate that
    # equates msg.value with a modeled ABI parameter (or a literal) is therefore
    # an input-construction constraint, not an ambient environment blocker. This
    # remains fail-closed for expressions whose value provenance is not modeled.
    transaction_value_binding = re.fullmatch(
        r"msg\.value\s*==\s*(?P<rhs>[A-Za-z_]\w*|(?:0x[0-9A-Fa-f]+|\d+))|"
        r"(?P<lhs>[A-Za-z_]\w*|(?:0x[0-9A-Fa-f]+|\d+))\s*==\s*msg\.value",
        predicate.strip(),
    )
    if transaction_value_binding:
        value_name = transaction_value_binding.group("rhs") or transaction_value_binding.group("lhs")
        if value_name in parameter_names or value_name.isdigit() or value_name.startswith("0x"):
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
    bound_call_names = identifiers & call_bound_locals
    if bound_call_names:
        binding_by_name = dict(function.execution_value_bindings)
        non_deterministic = {
            name for name in bound_call_names
            if not _is_deterministic_expression(binding_by_name.get(name, ""))
        }
        if not non_deterministic:
            return True
        if "callback_state_order_reachability" in execution_capabilities:
            call_result_guard = bool(
                re.fullmatch(
                    r"!\s*[A-Za-z_]\w*|"
                    r"[A-Za-z_]\w*\s*(?:==|!=)\s*(?:true|false|0|1)",
                    predicate.strip(),
                )
            )
            if call_result_guard and all(
                re.search(r"\.\w+\s*\(", binding_by_name[name])
                for name in non_deterministic
            ):
                return True
        return False
    return True


def _source_function_body(contract: ContractModel, function: FunctionModel) -> str:
    """Return one modeled function body from source using its recorded line."""
    try:
        source = _strip_comments(Path(contract.source).read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, UnicodeError):
        return ""
    declaration = re.compile(r"\bfunction\s+" + re.escape(function.name) + r"\s*\(")
    candidates = list(declaration.finditer(source))
    if not candidates:
        return ""
    target = min(candidates, key=lambda match: abs(source.count("\n", 0, match.start()) + 1 - function.line))
    opening = source.find("{", target.end())
    if opening < 0:
        return ""
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[opening + 1:index]
    return source[opening + 1:]


def _constructor_state_equalities(
    contract: ContractModel,
) -> dict[str, tuple[str, ...]]:
    """Collect source-backed constructor state equalities across inheritance."""
    source_path = Path(contract.source).resolve()
    project_root = next(
        (
            parent
            for parent in (source_path.parent, *source_path.parents)
            if any((parent / marker).exists() for marker in ("foundry.toml", "package.json", "remappings.txt"))
        ),
        source_path.parent,
    )
    facts: dict[str, list[str]] = {}
    visited: set[Path] = set()

    def constructor_body(source: str) -> str:
        match = re.search(r"\bconstructor\s*\(", source)
        if not match:
            return ""
        opening = source.find("(", match.start())
        depth = 0
        closing = None
        for index in range(opening, len(source)):
            char = source[index]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    closing = index
                    break
        if closing is None:
            return ""
        brace = source.find("{", closing)
        if brace < 0:
            return ""
        depth = 0
        for index in range(brace, len(source)):
            char = source[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return source[brace + 1:index]
        return ""

    def visit(path: Path, inherited_names: tuple[str, ...]) -> None:
        path = path.resolve()
        if path in visited or not path.is_file():
            return
        visited.add(path)
        try:
            source = _strip_comments(path.read_text(encoding="utf-8"))
            models = parse_solidity(path, include_inherited=False)
        except (OSError, UnicodeError):
            return
        model = models[0] if models else None
        state_names = set(model.state_variables if model is not None else ())
        body = constructor_body(source)
        for state in state_names:
            match = re.search(
                rf"\b{re.escape(state)}(?:\[[^;{{}}]+\])?\s*=\s*([^;]+);",
                body,
            )
            if match:
                value = re.sub(r"\s+", " ", match.group(1)).strip()
                facts.setdefault(state, []).append(value)
        for inherited_name in inherited_names:
            try:
                resolved = _resolve_inherited_contract_source(project_root, path, inherited_name)
            except (OSError, UnicodeError):
                continue
            if resolved is not None:
                try:
                    base_models = parse_solidity(resolved, include_inherited=False)
                    base_names = base_models[0].inherits if base_models else ()
                except (OSError, UnicodeError):
                    base_names = ()
                visit(resolved, base_names)

    visit(source_path, contract.inherits)
    return {name: tuple(dict.fromkeys(values)) for name, values in facts.items()}


def _constructor_state_predicate_satisfied(
    contract: ContractModel,
    predicate: str,
) -> bool:
    """Check simple state predicates against inherited constructor provenance."""
    facts = _constructor_state_equalities(contract)
    normalized = re.sub(r"\s+", " ", predicate).strip()
    for state, values in facts.items():
        for value in values:
            if re.fullmatch(
                rf"{re.escape(state)}\s*==\s*{re.escape(value)}",
                normalized,
            ) or re.fullmatch(
                rf"{re.escape(value)}\s*==\s*{re.escape(state)}",
                normalized,
            ):
                return True
            if re.fullmatch(rf"!{re.escape(state)}", normalized) and value in {"false", "0", "address(0)"}:
                return True
    return False


def _classify_internal_predicate(
    contract: ContractModel,
    callee: FunctionModel,
    predicate: str,
) -> str:
    """Classify a propagated prerequisite from the callee's modeled provenance.

    Classification is descriptive only. It must not turn a discovered
    prerequisite into evidence that the prerequisite is satisfiable.
    """
    normalized = predicate.lower()
    binding_by_name = dict(callee.execution_value_bindings)
    predicate_names = set(re.findall(r"\b[A-Za-z_]\w*\b", predicate))

    # A cryptographic witness may be derived through several deterministic
    # locals. Follow modeled value provenance transitively rather than requiring
    # the guard variable itself to contain a crypto keyword.
    # Hashing is not, by itself, a cryptographic witness requirement.
    # Deterministic builtins such as keccak256/sha256 can be satisfied by
    # constructing their inputs when the predicate is otherwise a local/input
    # constraint. Reserve the witness category for predicates that require a
    # secret/signature/proof/recovery relationship.
    crypto_terms = (
        "signature", "ecrecover", "ecdsa", "proof", "typeddata",
        "domainseparator", "recover",
    )
    visited: set[str] = set()

    def has_crypto_provenance(name: str, depth: int = 0) -> bool:
        if depth > 8 or name in visited:
            return False
        visited.add(name)
        expression = binding_by_name.get(name, "")
        if not expression:
            return False
        normalized_expression = expression.lower()
        if any(term in normalized_expression for term in crypto_terms):
            return True
        identifiers = set(re.findall(r"\b[A-Za-z_]\w*\b", expression))
        return any(has_crypto_provenance(identifier, depth + 1) for identifier in identifiers)

    for name in predicate_names:
        if has_crypto_provenance(name):
            return "cryptographic_witness"

    if any(term in normalized for term in (
        "signature", "recover", "ecrecover", "ecdsa",
        "proof", "nonce", "typeddata", "domainseparator",
    )):
        return "cryptographic_witness"

    # Ambient blockchain context is neither caller input nor persistent target
    # state. It requires a generic execution-context capability before it can
    # be treated as constructible.
    if re.search(r"\b(?:block\.timestamp|block\.number|block\.chainid|block\.prevrandao|tx\.timestamp|now)\b", predicate):
        return "execution_context"

    state_names = set(contract.state_variables)
    try:
        source_text = Path(contract.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        source_text = ""
    state_decl = re.compile(
        r"(?m)^\s*(?:mapping\s*\([^;{}]+\)|(?:uint|int|address|bool|bytes(?:\d+)?))\s+"
        r"(?:(?:public|private|internal|external|immutable|constant)\s+)*([A-Za-z_]\w*)\s*;"
    )
    for match in state_decl.finditer(source_text):
        state_names.add(match.group(1))
    # Keep a deliberately broader source-backed fallback for compact or
    # modifier-qualified declarations that the primary declaration grammar
    # cannot capture. This remains bounded to the current target source unit.
    broad_state_decl = re.compile(
        r"\b(?:mapping\s*\([^;{}]+\)|(?:uint|int|address|bool|bytes(?:\d+)?))\s+"
        r"(?:(?:public|private|internal|external|immutable|constant)\s+)*([A-Za-z_]\w*)\s*;"
    )
    state_names.update(match.group(1) for match in broad_state_decl.finditer(source_text))
    # Final bounded source-scope pass. Parse brace depth separately from
    # declaration matching so declaration capture groups remain unambiguous.
    primitive_state_decl = re.compile(
        r"\b(?:mapping\s*\([^;{}]+\)|(?:uint|int|address|bool|bytes(?:\d+)?))\s+"
        r"(?:(?:public|private|internal|external|immutable|constant)\s+)*([A-Za-z_]\w*)\s*;"
    )
    depth = 0
    cursor = 0
    for token in re.finditer(r"[{}]", source_text):
        segment = source_text[cursor:token.start()]
        if depth == 1:
            state_names.update(match.group(1) for match in primitive_state_decl.finditer(segment))
        depth = depth + 1 if token.group(0) == "{" else max(0, depth - 1)
        cursor = token.end()
    if depth == 1:
        state_names.update(match.group(1) for match in primitive_state_decl.finditer(source_text[cursor:]))
    identifiers = set(re.findall(r"\b[A-Za-z_]\w*\b", predicate))
    if identifiers & state_names or "$." in predicate:
        return "state_observation"
    # A local guard can be a thin wrapper around a persistent-state lookup,
    # such as verifier = verifierMap[verifierId] followed by
    # address(verifier) != address(0). Preserve that state provenance so the
    # generic state-setup solver can connect the guard to a constructible
    # writer instead of treating the value as an opaque local execution gap.
    for local_name in identifiers.intersection(binding_by_name):
        binding = binding_by_name.get(local_name, "")
        binding_names = set(re.findall(r"\b[A-Za-z_]\w*\b", binding))
        if binding_names.intersection(state_names):
            return "state_observation"
    # Last source-backed declaration check for compact/generated fixtures.
    # This intentionally checks only declarations whose type is a Solidity
    # persistent-value primitive and never treats an arbitrary identifier as
    # state merely because it appears in the predicate.
    declared_state_names = {
        match.group(1)
        for match in re.finditer(
            r"\b(?:bool|address|uint(?:\d+)?|int(?:\d+)?|bytes(?:\d+)?)\s+"
            r"(?:(?:public|private|internal|external|immutable|constant)\s+)*"
            r"([A-Za-z_]\w*)\s*;",
            source_text,
        )
    }
    if identifiers.intersection(declared_state_names):
        return "state_observation"

    # Unary state guards such as !verified are common in compact target
    # sources. Preserve their state provenance even when the parser/model did
    # not populate contract.state_variables.
    for state_candidate in re.findall(r"\b!\s*([A-Za-z_]\w*)\b", predicate):
        if re.search(
            rf"\b(?:bool|address|uint(?:\d+)?|int(?:\d+)?|bytes(?:\d+)?)\s+"
            rf"(?:public|private|internal|external|immutable|constant\s+)*"
            rf"{re.escape(state_candidate)}\s*;",
            source_text,
        ):
            return "state_observation"

    # Callee-local values are not automatically caller inputs. Keep their
    # provenance conservative unless a deterministic input binding proves so.
    local_names = set(binding_by_name)
    if identifiers & local_names:
        return "local_execution"

    # msg.value is ambient call context, but retain the historical
    # descriptive category for this boundary; satisfiability is still handled
    # by the generic experiment-constraint classifier.
    if "msg.value" in normalized:
        return "unknown"
    return "input_construction"


def _internal_execution_requirements(
    contract: ContractModel,
    function: FunctionModel,
    *,
    max_depth: int = 4,
    execution_capabilities: frozenset[str] = frozenset(),
) -> tuple[ExecutionRequirement, ...]:
    """Propagate modeled internal-call prerequisites into caller readiness.

    Internal callees use the same execution-predicate language as top-level
    actions. Reuse the generic input/local constraint classifier here rather
    than treating every propagated predicate as an unresolved environment
    blocker. State, ambient-context, and unresolved local predicates remain
    fail-closed.
    """
    functions = tuple(dict.fromkeys((*contract.functions, *contract.inherited_functions)))
    by_name = {item.name: item for item in functions if item is not None}
    ignored = {"if", "for", "while", "require", "revert", "assert", "emit", "return", "new", "delete", "unchecked", "abi", "keccak256", "sha256", "ecrecover"}
    # Internal guards can depend on persistent state that is not directly
    # named by the top-level action. Reuse the same target-derived setup
    # surface used by the recursive readiness planner. A constructible writer
    # is evidence that the state can be established; it is not evidence that
    # the security hypothesis is true.
    internal_state_setup_candidates = _internal_state_setup_candidates(contract, function)
    constructible_internal_states = {
        candidate.source.rsplit(":", 1)[-1]
        for candidate in internal_state_setup_candidates
        if candidate.status == "constructible"
    }
    results: list[ExecutionRequirement] = []
    visited: set[tuple[str, int]] = set()
    def call_arguments(source: str, opening: int) -> tuple[str, ...]:
        depth = 0
        start = opening + 1
        values: list[str] = []
        for index in range(opening + 1, len(source)):
            char = source[index]
            if char == "(":
                depth += 1
            elif char == ")":
                if depth == 0:
                    value = source[start:index].strip()
                    if value:
                        values.append(value)
                    return tuple(values)
                depth -= 1
            elif char == "," and depth == 0:
                values.append(source[start:index].strip())
                start = index + 1
        return ()

    def visit(caller: FunctionModel, depth: int) -> None:
        if depth > max_depth or (caller.name, depth) in visited:
            return
        visited.add((caller.name, depth))
        body = _source_function_body(contract, caller)
        # Model-only callers used by analysis integrations may not have a
        # readable source path. Preserve the explicit internal-call relation
        # emitted by the Solidity model so readiness propagation remains
        # generic instead of silently dropping the callee prerequisites.
        if body:
            call_sites = tuple(
                (match.group(1), match.end() - 1)
                for match in re.finditer(r"\b([A-Za-z_]\w*)\s*\(", body)
            )
        else:
            call_sites = tuple((name, None) for name in caller.internal_calls)
        if not call_sites:
            return
        seen_names: set[str] = set()
        for name, opening in call_sites:
            if name in ignored or name == caller.name or name in seen_names:
                continue
            callee = by_name.get(name)
            if callee is None:
                continue
            seen_names.add(name)
            actual_arguments = call_arguments(body, opening) if opening is not None else ()
            caller_parameter_names = {parameter.name for parameter in caller.parameters if parameter.name}
            forwarded_caller_inputs = {
                parameter.name
                for parameter, argument in zip(callee.parameters, actual_arguments)
                if parameter.name and argument.strip() in caller_parameter_names
            }
            modeled_predicates = list(dict.fromkeys((*callee.execution_predicates, *callee.state_predicates)))
            # Source-backed fallback for compact models that omit simple
            # require(...) guards from the predicate collections.
            callee_body = _source_function_body(contract, callee)
            for require_match in re.finditer(r"\brequire\s*\(\s*(?P<predicate>[^;]+?)\s*\)", callee_body):
                source_predicate = require_match.group("predicate").strip()
                if source_predicate and source_predicate not in modeled_predicates:
                    modeled_predicates.append(source_predicate)
            for predicate in modeled_predicates:
                kind = "internal_execution_predicate"
                category = (
                    "state_observation"
                    if predicate in callee.state_predicates
                    else _classify_internal_predicate(contract, callee, predicate)
                )
                try:
                    direct_source = Path(contract.source).read_text(encoding="utf-8")
                except (OSError, UnicodeError):
                    direct_source = ""
                unary_state = re.findall(r"\b!\s*([A-Za-z_]\w*)\b", predicate)
                parameter_names = {parameter.name for parameter in callee.parameters if parameter.name}
                local_names = {
                    *dict(callee.execution_value_bindings),
                    *(parameter.name for parameter in callee.return_parameters if parameter.name),
                }
                simple_boolean_state = re.fullmatch(r"!?[A-Za-z_]\w*", predicate.strip())
                if unary_state and any(
                    name not in parameter_names and name not in local_names
                    for name in unary_state
                ):
                    category = "state_observation"
                elif simple_boolean_state and simple_boolean_state.group(0).lstrip("!").strip() not in parameter_names and simple_boolean_state.group(0).lstrip("!").strip() not in local_names:
                    category = "state_observation"
                constraint = _is_experiment_constraint(
                    contract,
                    callee,
                    predicate,
                    execution_capabilities,
                )
                if category in {"cryptographic_witness", "execution_context"}:
                    constraint = False
                # A forwarded caller input remains constructible when the
                # callee predicate is otherwise a generic input/local constraint.
                # The caller experiment owns materialization of that parameter;
                # forwarding provenance is evidence of data flow, not a reason
                # to turn an already-satisfiable predicate back into a blocker.
                predicate_state_names = {
                    name for name in re.findall(r"\b[A-Za-z_]\w*\b", predicate)
                    if name in set(contract.state_variables)
                }
                # Solidity parsing can leave state_variables empty for compact
                # source-backed models. Recover persistent-value declarations from
                # the target source so default-state reasoning remains generic.
                try:
                    source_state = Path(contract.source).read_text(encoding="utf-8")
                except (OSError, UnicodeError):
                    source_state = ""
                source_state_decl = re.compile(
                    r"\b(?:mapping\s*\([^;{}]+\)|(?:uint|int|address|bool|bytes(?:\d+)?))\s+"
                    r"(?:(?:public|private|internal|external|immutable|constant)\s+)*([A-Za-z_]\w*)\s*;"
                )
                source_state_names = {
                    match.group(1) for match in source_state_decl.finditer(source_state)
                }
                predicate_state_names.update(
                    name for name in re.findall(r"\b[A-Za-z_]\w*\b", predicate)
                    if name in source_state_names
                )
                # Internal predicates may name a local whose value is sourced
                # from persistent state. Include those state names in the setup
                # relation so a constructible mapping writer can satisfy the
                # prerequisite without target-specific knowledge.
                predicate_identifiers = set(re.findall(r"\b[A-Za-z_]\w*\b", predicate))
                binding_map = dict(callee.execution_value_bindings)
                for local_name in predicate_identifiers.intersection(binding_map):
                    predicate_state_names.update(
                        name for name in re.findall(r"\b[A-Za-z_]\w*\b", binding_map[local_name])
                        if name in set(contract.state_variables)
                    )
                state_setup = (
                    category == "state_observation"                    and bool(predicate_state_names.intersection(constructible_internal_states))
                )
                default_state = (
                    category == "state_observation"
                    and any(
                        _state_observation_has_default_solution(contract, callee, state)
                        for state in predicate_state_names
                    )
                )
                constructor_state = (
                    category == "state_observation"
                    and _constructor_state_predicate_satisfied(contract, predicate)
                )
                state_observation = (
                    category == "state_observation"
                    and plan_namespaced_state_observation(contract, callee, predicate) is not None
                )
                detail = {
                    "state_observation": "internal callee prerequisite requires generic state observation/setup",
                    "input_construction": "internal callee prerequisite requires generic experiment-input construction",
                    "cryptographic_witness": "internal callee prerequisite requires generic cryptographic witness construction",
                    "execution_context": "internal callee prerequisite requires generic blockchain execution context",
                    "local_execution": "internal callee prerequisite depends on a callee-local value whose provenance is not yet constructible",
                }.get(
                    category,
                    "internal callee prerequisite could not be classified by the generic readiness model; "
                    "the prerequisite remains unresolved until its provenance/category is established",
                )
                capability_constraint = (
                    category == "execution_context"
                    and "callback_state_order_reachability" in execution_capabilities
                    and dict(callee.execution_predicate_polarities).get(predicate) == "must_not_hold"
                    and bool(
                        re.search(
                            r"\bblock\.timestamp\s*(?:>|>=|<|<=)",
                            predicate,
                        )
                    )
                )
                if constraint or capability_constraint or state_observation or state_setup or default_state or constructor_state:
                    status = "constraint"
                    if capability_constraint and not constraint:
                        detail = (
                            "callback execution-context adapter can satisfy this guarded "
                            "ambient-time prerequisite without changing target semantics"
                        )
                    elif default_state:
                        detail = (
                            "fresh target state satisfies this persistent prerequisite by its "
                            "modeled default value; the experiment must preserve that state"
                        )
                    elif constructor_state:
                        detail = (
                            "inherited/current constructor source establishes this persistent "
                            "state equality; the experiment must preserve that constructor state"
                        )
                    elif state_setup:
                        detail = (
                            "target-derived state setup planner found a constructible writer "
                            "for this persistent prerequisite; the experiment must apply and "
                            "verify that transition before the security assertion"
                        )
                    elif state_observation:
                        detail = (
                            "compiler/source-backed ERC-7201 state observation can verify this "
                            "mapping prerequisite before the experiment"
                        )
                    else:
                        detail = (
                            "internal callee prerequisite is a pure input/local constraint; "
                            "the caller experiment must construct values satisfying it"
                        )
                else:
                    status = "unresolved"
                results.append(ExecutionRequirement(
                    kind,
                    f"{callee.name}: {predicate}",
                    f"{caller.name}:internal-call->{callee.name}",
                    status,
                    detail,
                    category=category,
                ))
            visit(callee, depth + 1)
    visit(function, 0)
    return tuple(dict.fromkeys(results))


def _call_arguments_from_expression(expression: str) -> tuple[str, ...]:
    """Split one modeled Solidity call's arguments without target-specific parsing."""
    opening = expression.find("(")
    if opening < 0:
        return ()
    depth = 0
    start = opening + 1
    values: list[str] = []
    for index in range(opening + 1, len(expression)):
        char = expression[index]
        if char == "(":
            depth += 1
        elif char == ")":
            if depth == 0:
                value = expression[start:index].strip()
                if value:
                    values.append(value)
                return tuple(values)
            depth -= 1
        elif char == "," and depth == 0:
            values.append(expression[start:index].strip())
            start = index + 1
    return ()


def _modeled_call_return_has_constructible_branch(
    contract: ContractModel,
    predicate: str,
) -> bool:
    """Recognize source-derived call branches satisfiable by generic ABI inputs.

    A modeled helper can expose a normal-path branch such as return root == 0.
    When the caller invokes that helper with a primitive ABI value, zero is a
    generic deterministic input choice. This is evidence that the call-shaped
    execution predicate is an input constraint rather than a capability gap.
    """
    match = re.match(r"^\s*(?P<name>[A-Za-z_]\w*)\s*\(", predicate)
    if not match:
        return False
    callee = next(
        (
            item
            for item in (*contract.functions, *contract.inherited_functions)
            if item.name == match.group("name")
        ),
        None,
    )
    if callee is None or not callee.return_expressions:
        return False
    arguments = _call_arguments_from_expression(predicate)
    if not arguments:
        return False
    for return_expression in callee.return_expressions:
        for parameter_index, parameter in enumerate(callee.parameters):
            if parameter_index >= len(arguments):
                continue
            base = parameter.type.strip().split()[0].rstrip("[]")
            primitive = (
                base in {"address", "bool", "string", "bytes"}
                or base.startswith(("uint", "int", "bytes"))
            )
            if not primitive:
                continue
            if re.search(
                rf"\b{re.escape(parameter.name)}\s*==\s*(?:0|false|address\(0\))",
                return_expression,
            ):
                return True
    return False



def _cryptographic_witness_route(
    contract: ContractModel,
    predicate: str,
) -> str:
    """Expose target-derived provenance behind a cryptographic predicate.

    This is planning evidence only. It deliberately does not synthesize a
    cryptographic witness or declare the predicate satisfiable.
    """
    builtin_calls = {
        "abi.decode", "abi.encode", "abi.encodePacked", "abi.encodeWithSelector",
        "abi.encodeWithSignature", "abi.encodeCall", "keccak256", "sha256",
        "ripemd160", "ecrecover", "addmod", "mulmod",
    }
    def modeled_calls(expression: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
        discovered: list[tuple[str, tuple[str, ...]]] = []
        for match in re.finditer(
            r"(?P<head>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?)\s*\(",
            expression,
        ):
            head = match.group("head")
            if head in builtin_calls:
                continue
            arguments = _call_arguments_from_expression(expression[match.start():])
            discovered.append((head, arguments))
        return tuple(dict.fromkeys(discovered))

    calls = modeled_calls(predicate)
    if not calls:
        return (
            "cryptographic predicate has no non-builtin call-shaped producer "
            "in the current model; witness provenance remains unresolved"
        )

    functions = tuple(dict.fromkeys((*contract.functions, *contract.inherited_functions)))
    by_name = {item.name: item for item in functions}
    routes = []
    for call, arguments in calls:
        method = call.rsplit(".", 1)[-1]
        callee = by_name.get(method)
        if callee is not None:
            bindings = [
                f"{parameter.name} <- {argument}"
                for parameter, argument in zip(callee.parameters, arguments)
                if parameter.name
            ]
            routes.append(
                f"target-derived verifier {call}; source={callee.name}; "
                f"inputs={', '.join(bindings) or 'arguments not positionally resolved'}; "
                f"returns={', '.join(callee.return_expressions) or '<return expression not modeled>'}"
            )
        elif "." in call:
            routes.append(
                f"external verifier {call}; receiver={call.rsplit('.', 1)[0]}; "
                "interface/endpoint must be resolved before witness construction"
            )
        else:
            routes.append(
                f"unresolved verifier/proof producer {call}; "
                "no compiler-model-resolved local function is available"
            )
    return "; ".join(dict.fromkeys(routes))


def _execution_requirements(
    contract: ContractModel,
    function: FunctionModel,
    execution_capabilities: frozenset[str] = frozenset(),
) -> tuple[ExecutionRequirement, ...]:
    polarities = dict(function.execution_predicate_polarities)
    requirements: list[ExecutionRequirement] = []
    setup_candidates = _state_setup_candidates(contract, function)
    setup_states = {
        part
        for candidate in setup_candidates
        for part in candidate.source.rsplit(":state:", 1)[-1:]
        if part
    }
    for predicate in function.execution_predicates:
        polarity = polarities.get(predicate, "unknown")
        detail = {
            "must_hold": "execution predicate must hold for the normal security-relevant path",
            "must_not_hold": "execution predicate is a guarded revert condition and must not hold",
            "unknown": "execution predicate polarity could not be established statically",
        }.get(polarity, "execution predicate polarity is unknown")
        category = _classify_internal_predicate(contract, function, predicate)
        modeled_call_branch = _modeled_call_return_has_constructible_branch(contract, predicate)
        status = (
            "constraint"
            if modeled_call_branch
            or _is_experiment_constraint(contract, function, predicate, execution_capabilities)
            else "required"
        )
        # Execution predicates can encode persistent state just like explicit
        # state_predicates. Reuse the existing generic setup solver rather than
        # leaving those guards permanently blocked merely because extraction
        # classified them as execution-path predicates.
        if category == "state_observation":
            referenced_states = set(re.findall(r"\b[A-Za-z_]\w*\b", predicate))
            if referenced_states.intersection(set(setup_states)):
                status = "constraint"
                detail = (
                    "execution predicate references persistent state with a "
                    "target-derived constructible setup transition"
                )
        if category == "cryptographic_witness" and not modeled_call_branch:
            # A negative verification predicate is a constructible prerequisite
            # when the target's own ABI/type model can materialize an explicitly
            # empty/zero signature witness. The evidence must come from the
            # source-backed type materializer; do not infer this from names alone.
            negative_crypto = bool(
                re.fullmatch(
                    r"!\s*[A-Za-z_]\w*|[A-Za-z_]\w*\s*==\s*false",
                    predicate.strip(),
                )
            )
            negative_witness = False
            if negative_crypto:
                try:
                    from .experiment_inputs import prove_parameter_materialization
                    proofs = prove_parameter_materialization(function.parameters, contract)
                    if proofs:
                        provenance = " ".join(
                            item
                            for proof in proofs
                            for item in proof.provenance
                        ).lower()
                        expression = " ".join(proof.expression for proof in proofs).lower()
                        has_crypto_field = any(
                            token in provenance
                            for token in ("signature", ".sig:", ".v:", ".r:", ".s:", "proof")
                        )
                        has_empty_witness = (
                            'bytes("")' in expression
                            or "bytes32(0)" in expression
                            or re.search(r"\bv\s*[:=].*?0", expression) is not None
                        )
                        negative_witness = has_crypto_field and has_empty_witness
                except (OSError, ValueError, TypeError):
                    negative_witness = False
            if negative_witness:
                status = "constraint"
                detail = (
                    "source-backed recursive ABI materialization provides a "
                    "deterministic empty/zero cryptographic witness for the "
                    "target's explicit negative verification branch"
                )
            else:
                status = "required"
                detail = (
                    "cryptographic witness prerequisite; "
                    + _cryptographic_witness_route(contract, predicate)
                    + ". No witness is synthesized at readiness time."
                )
        if status == "constraint":
            detail = (
                "source-derived helper return branch is satisfiable by a generic "
                "primitive ABI input; the generated experiment must satisfy it before "
                "the security-relevant assertion"
                if modeled_call_branch
                else
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
                category=category,
            )
        )
    requirements.extend(
        _internal_execution_requirements(
            contract,
            function,
            execution_capabilities=execution_capabilities,
        )
    )
    return tuple(requirements)


def _state_requirements(
    contract: ContractModel,
    function: FunctionModel,
) -> tuple[ExecutionRequirement, ...]:
    polarities = dict(function.state_predicate_polarities)
    requirements: list[ExecutionRequirement] = []
    setup_actions = constructible_state_setup_plan(contract, function)
    setup_states = {
        part
        for action in setup_actions
        for part in action.provenance
        if part
    }
    for predicate in function.state_predicates:
        state_names = set(re.findall(r"\b([A-Za-z_]\w*)\b", predicate))
        default_solution = any(
            _state_observation_has_default_solution(contract, function, state)
            for state in state_names
        )
        setup_solution = bool(setup_states.intersection(state_names))
        status = "constraint" if default_solution or setup_solution else "required"
        requirements.append(
            ExecutionRequirement(
                "state_predicate",
                predicate,
                f"{function.name}:body",
                status,
                (
                    "state predicate has a target-derived constructible setup transition; "
                    "the generated experiment must apply that transition before the security assertion"
                    if setup_solution
                    else "state predicate is satisfied by the modeled default state; "
                    "the generated experiment must preserve that default"
                    if default_solution
                    else {
                        "must_hold": "state predicate must hold for the normal execution path",
                        "must_not_hold": "state predicate is a guarded revert condition and must not hold",
                        "unknown": "state predicate polarity could not be established statically",
                    }.get(polarities.get(predicate, "unknown"), "state predicate polarity is unknown")
                ),
            )
        )
    return tuple(requirements)


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

def _state_names_from_internal_predicates(
    contract: ContractModel,
    function: FunctionModel,
    *,
    max_depth: int = 4,
) -> tuple[str, ...]:
    """Discover persistent state referenced by internal execution predicates."""
    state_names = set(contract.state_variables)
    try:
        source_text = Path(contract.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        source_text = ""
    state_names.update(
        match.group(1)
        for match in re.finditer(
            r"\b(?:mapping\s*\([^;{}]+\)|(?:bool|address|uint(?:\d+)?|int(?:\d+)?|bytes(?:\d+)?))\s+"
            r"(?:(?:public|private|internal|external|immutable|constant)\s+)*([A-Za-z_]\w*)\s*;",
            source_text,
        )
    )
    functions = {item.name: item for item in (*contract.functions, *contract.inherited_functions) if item is not None}
    discovered: list[str] = []
    visited: set[tuple[str, int]] = set()

    def visit(current: FunctionModel, depth: int) -> None:
        if depth > max_depth or (current.name, depth) in visited:
            return
        visited.add((current.name, depth))
        # State dependencies may be hidden behind a local producer rather than
        # appearing directly in the guard. For example, a verifier guard can be
        # \"address(verifier) != address(0)\" while verifier is produced from
        # verifierMap[verifierId]. Follow modeled value/return provenance so the
        # recursive setup solver sees the real persistent state surface.
        expressions = list(current.execution_predicates) + list(current.return_expressions)
        expressions.extend(expression for _local, expression in current.execution_value_bindings)
        for expression in expressions:
            for name in re.findall(r"\b[A-Za-z_]\w*\b", expression):
                if name in state_names and name not in discovered:
                    discovered.append(name)
        body = _source_function_body(contract, current)
        seen: set[str] = set()
        for match in re.finditer(r"\b([A-Za-z_]\w*)\s*\(", body):
            callee = functions.get(match.group(1))
            if callee is None or callee.name in seen:
                continue
            seen.add(callee.name)
            visit(callee, depth + 1)

    visit(function, 0)
    return tuple(discovered)


def _internal_state_setup_candidates(
    contract: ContractModel,
    function: FunctionModel,
    semantic_evidence: tuple[SemanticRelationshipEvidence, ...] = (),
) -> tuple[ExecutionRequirement, ...]:
    """Expose constructible writers for state referenced only by internal callees."""
    state_names = _state_names_from_internal_predicates(contract, function)
    if not state_names:
        return ()
    effects = build_state_effect_index(semantic_evidence)
    candidates: list[ExecutionRequirement] = []
    functions = tuple(dict.fromkeys((*contract.functions, *contract.inherited_functions)))
    for state in state_names:
        for writer in functions:
            if writer.name == function.name or writer.visibility not in {"public", "external"}:
                continue
            semantic_writes = state_writes_for_function(effects, writer.name)
            writer_body = _source_function_body(contract, writer)
            source_write = bool(
                re.search(
                    rf"\b{re.escape(state)}\s*(?:\[[^\]]+\])?\s*(?:\+=|-=|=)",
                    writer_body,
                )
            )
            touched = state in writer.writes or (semantic_writes is not None and state in semantic_writes) or source_write or any(
                (
                    (str(call[0]) if isinstance(call, (tuple, list)) and call else str(call).rsplit(".", 1)[0])
                    == state
                    and
                    (str(call[1]) if isinstance(call, (tuple, list)) and len(call) > 1 else str(call).rsplit(".", 1)[-1] if "." in str(call) else "*")
                ) and (
                    (str(call[1]) if isinstance(call, (tuple, list)) and len(call) > 1 else str(call).rsplit(".", 1)[-1] if "." in str(call) else "*")
                    in {"push", "pop"}
                )
                for call in writer.external_calls
            )
            if not touched:
                continue
            primitive_abi = all(
                parameter.type.strip().split()[0].rstrip("[]") in {"address", "bool", "string", "bytes"}
                or parameter.type.strip().split()[0].rstrip("[]").startswith(("uint", "int", "bytes"))
                for parameter in writer.parameters
            )
            authorization_requirements = tuple(
                item for item in _caller_requirements(writer, contract)
                if item.status == "required"
            )
            status = (
                "constructible"
                if primitive_abi and not authorization_requirements
                else "unresolved"
            )
            detail = (
                f"target-derived internal predicate references persistent state {state}; "
                f"writer {writer.name} has a constructible primitive ABI"
                if primitive_abi and not authorization_requirements else
                f"target-derived internal predicate references persistent state {state}; "
                f"writer {writer.name} has unresolved authorization prerequisites: "
                + ", ".join(item.subject for item in authorization_requirements)
                if primitive_abi else
                f"target-derived internal predicate references persistent state {state}; "
                f"writer {writer.name} has non-primitive parameters"
            )
            candidates.append(ExecutionRequirement(
                "internal_state_setup_candidate",
                writer.name,
                f"{function.name}:internal-state:{state}",
                status,
                detail,
                category="state_observation",
            ))
    return tuple(dict.fromkeys(candidates))

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
    state_names.update(_state_names_from_internal_predicates(contract, function))
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
    all_functions = tuple(dict.fromkeys((*contract.functions, *contract.inherited_functions)))
    for state in state_names:
        for writer in all_functions:
            if writer.name == function.name or writer.visibility not in {"public", "external"}:
                continue
            semantic_writes = state_writes_for_function(semantic_effects, writer.name)
            touched = state in writer.writes or (semantic_writes is not None and state in semantic_writes) or any(
                (
                    (str(call[0]) if isinstance(call, (tuple, list)) and call else str(call).rsplit(".", 1)[0])
                    == state
                    and
                    (str(call[1]) if isinstance(call, (tuple, list)) and len(call) > 1 else str(call).rsplit(".", 1)[-1] if "." in str(call) else "*")
                ) and (
                    (str(call[1]) if isinstance(call, (tuple, list)) and len(call) > 1 else str(call).rsplit(".", 1)[-1] if "." in str(call) else "*")
                    in {"push", "pop"}
                )
                for call in writer.external_calls
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
            authorization_requirements = tuple(
                item for item in _caller_requirements(writer, contract)
                if item.status == "required"
            )
            status = (
                "constructible"
                if primitive_abi and not runtime_dependencies
                else "unresolved"
            )
            if not primitive_abi:
                detail = f"candidate transition {writer.name} has non-primitive parameters and cannot be synthesized generically"
            elif runtime_dependencies:
                detail = (
                    f"candidate transition {writer.name} touches modeled prerequisite state {state} "
                    "but has unresolved runtime dependencies"
                )
            elif authorization_requirements:
                detail = (
                    f"candidate transition {writer.name} touches modeled prerequisite state {state} "
                    "but its caller authorization is unresolved: "
                    + ", ".join(item.subject for item in authorization_requirements)
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


def _state_observation_has_default_solution(
    contract: ContractModel,
    function: FunctionModel,
    state: str,
) -> bool:
    """Recognize state predicates whose required value is Solidity's zero/default value."""
    functions = {item.name: item for item in (*contract.functions, *contract.inherited_functions)}
    visited: set[str] = set()

    def visit(current: FunctionModel) -> bool:
        if current.name in visited:
            return False
        visited.add(current.name)
        polarities = {
            **dict(current.execution_predicate_polarities),
            **dict(current.state_predicate_polarities),
        }
        # Compact/source-backed models can expose a guard in the Solidity body
        # without preserving its polarity metadata. A require(...) expression
        # is semantically a must-hold predicate at entry, so recover that
        # provenance generically instead of treating a default-state guard as
        # unresolved merely because the parser omitted the polarity field.
        body = _source_function_body(contract, current)
        source_require_predicates = {
            match.group("predicate").strip()
            for match in re.finditer(
                r"\brequire\s*\(\s*(?P<predicate>[^;]+?)\s*\)",
                body,
            )
        }
        for predicate in source_require_predicates:
            polarities.setdefault(predicate, "must_hold")
        modeled_predicates = tuple(
            dict.fromkeys(
                (*current.execution_predicates, *current.state_predicates, *source_require_predicates)
            )
        )
        for predicate in modeled_predicates:
            # Predicates recovered directly from require(...) are semantically
            # entry guards even when the compact parser omitted polarity
            # metadata. Model-backed predicates still require explicit polarity.
            if predicate not in source_require_predicates and polarities.get(predicate) != "must_hold":
                continue
            normalized = re.sub(r"\s+", " ", predicate).strip()
            def indexed_state_is_default(prefix: str) -> bool:
                if not normalized.startswith(prefix):
                    return False
                remainder = normalized[len(prefix):].lstrip()
                if not remainder.startswith("["):
                    return False
                while remainder.startswith("["):
                    depth = 0
                    end = None
                    for index, char in enumerate(remainder):
                        if char == "[":
                            depth += 1
                        elif char == "]":
                            depth -= 1
                            if depth == 0:
                                end = index
                                break
                            if depth < 0:
                                return False
                    if end is None:
                        return False
                    remainder = remainder[end + 1:].lstrip()
                return not remainder

            # A plain unary boolean guard such as !verified is the
            # Solidity zero/default-state form for a bool. It does not have
            # an index suffix, so it must be handled before the indexed-state
            # parser below.
            if normalized == f"!{state}":
                return True
            if normalized == f"{state} == false":
                return True
            if indexed_state_is_default(f"!{state}"):
                return True
            if normalized.startswith(f"{state}") and normalized.endswith("== false"):
                left = normalized[:-len("== false")].rstrip()
                if indexed_state_is_default(left):
                    return True
        body = _source_function_body(contract, current)
        for match in re.finditer(r"\b([A-Za-z_]\w*)\s*\(", body):
            callee = functions.get(match.group(1))
            if callee is not None and visit(callee):
                return True
        return False

    return visit(function)


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

    def planner_readiness(fn: FunctionModel) -> ExecutionReadiness:
        """Readiness view that deliberately excludes recursive state requirements."""
        return ExecutionReadiness(
            contract=contract.name,
            constructor_requirements=_constructor_requirements(contract),
            caller_requirements=_caller_requirements(fn, contract),
            runtime_requirements=_runtime_requirements(contract, fn),
            execution_requirements=(
                *_execution_requirements(contract, fn),
                *_execution_dataflow_requirements(contract, fn, semantic_evidence, frozenset()),
            ),
            state_setup_candidates=(
                *_state_setup_candidates(contract, fn, constraints, semantic_evidence),
                *_internal_state_setup_candidates(contract, fn, semantic_evidence),
            ),
        )

    def required_state_names(fn: FunctionModel) -> tuple[str, ...]:
        names = list(_state_names_from_predicates(fn))
        for predicate in fn.authorization_predicates:
            principal = _state_principal_from_predicate(predicate)
            if principal and principal in contract.state_variables and principal not in names:
                names.append(principal)
        predicates = list(fn.authorization_predicates)
        for modifier_name in fn.modifiers:
            modifier = next(
                (item for item in (*contract.modifiers, *contract.inherited_modifiers) if item.name == modifier_name),
                None,
            )
            if modifier is not None:
                predicates.extend(_authorization_predicates_from_body(modifier.body))
        for predicate in predicates:
            principal = _caller_principal_from_predicate(predicate)
            if principal and _caller_state_principal_provenance(contract, principal) and principal not in names:
                names.append(principal)
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
        for state in _state_names_from_internal_predicates(contract, fn):
            if state not in names:
                names.append(state)
        readiness = planner_readiness(fn)
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
        readiness = planner_readiness(fn)

        # A state-observation prerequisite is not itself a reason to abandon
        # planning when the target model already exposes a writer for that
        # exact state. The writer must still pass its own readiness checks below;
        # this is the boundary between "state is currently unknown" and "state
        # can be established by a verified target transition". Other unresolved
        # prerequisites remain hard blockers, and state with no writer remains
        # unresolved.
        planned_state_names = set(required_state_names(fn))
        default_satisfied_states = {
            state for state in planned_state_names
            if _state_observation_has_default_solution(contract, fn, state)
        }
        all_planned_state_names = set(planned_state_names)
        planned_state_names.difference_update(default_satisfied_states)
        state_writer_names = {
            state: tuple(writer.name for writer in writers_for(state))
            for state in planned_state_names
        }
        hard_blockers = []
        caller_principal_states = {
            principal
            for predicate in fn.authorization_predicates
            for principal in [_caller_principal_from_predicate(predicate)]
            if principal and _caller_state_principal_provenance(contract, principal)
        }
        for item in readiness.blockers:
            if (
                item.status == "unresolved"
                and item.kind == "caller_state_principal"
                and item.subject in caller_principal_states
            ):
                continue
            if (
                item.status == "unresolved"
                and item.category == "state_observation"
                and not any(
                    state in item.subject and state in default_satisfied_states
                    for state in all_planned_state_names
                )
                and any(
                    state in item.subject and state_writer_names.get(state)
                    for state in planned_state_names
                )
            ):
                continue
            hard_blockers.append(item)
        if hard_blockers:
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
        # The readiness surface is the authoritative evidence that a writer is
        # constructible.  The recursive planner still resolves nested state
        # prerequisites, but it must not discard an already-proven primitive
        # writer merely because re-inspecting that writer through a different
        # call-graph context loses provenance that was established at the
        # consumer boundary.  This is especially important for inherited
        # writers whose authorization/state model is assembled across contracts.
        constructible_candidates = {}
        for candidate in readiness.state_setup_candidates:
            if candidate.status != "constructible":
                continue
            marker = candidate.source.rsplit(":", 1)[-1]
            constructible_candidates.setdefault((marker, candidate.subject), candidate)

        for state in required_state_names(fn):
            if state in default_satisfied_states:
                continue
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

                # A constructible candidate has already passed the generic ABI,
                # runtime-dependency, and authorization checks. If that writer
                # has no additional state prerequisites of its own, it is safe
                # to consume that evidence directly instead of inventing a
                # second target-specific proof path.
                if constructible_candidates.get((state, writer.name)) is not None:
                    writer_states = tuple(
                        item
                        for item in (
                            *required_state_names(writer),
                            *_state_names_from_internal_predicates(contract, writer),
                        )
                        if not _state_observation_has_default_solution(contract, writer, item)
                    )
                    if not writer_states:
                        selected = (SetupAction(writer.name, caller_role(writer), (*stack, fn.name, state)),)
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
    execution_capabilities: frozenset[str] = frozenset(),
) -> ExecutionReadiness:
    """Derive target execution prerequisites without making vulnerability claims."""
    selected = function
    return ExecutionReadiness(
        contract=contract.name,
        constructor_requirements=_constructor_requirements(contract),
        caller_requirements=_caller_requirements(selected, contract) if selected else (),
        runtime_requirements=_runtime_requirements(contract, selected) if selected else (),
        execution_requirements=(
            (*_execution_requirements(contract, selected, execution_capabilities), *_execution_dataflow_requirements(contract, selected, semantic_evidence, execution_capabilities))
            if selected else ()
        ),
        state_requirements=(
            (*_state_requirements(contract, selected), *_constraint_state_requirements(selected, constraints))
            if selected else ()
        ),
        state_setup_candidates=(
            (*_state_setup_candidates(contract, selected, constraints, semantic_evidence),
             *_internal_state_setup_candidates(contract, selected, semantic_evidence))
            if selected else ()
        ),
    )
