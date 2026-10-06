from __future__ import annotations

"""Reachable Web2 security frontier.

This module deliberately does not classify vulnerabilities.  It turns already
reachable target-model evidence into security questions and keeps blocked
capabilities local to the branch that needs them.
"""

from dataclasses import dataclass
from enum import Enum

from .web2_model import Web2EndpointModel, Web2ObservationModel, Web2TargetModel


class SecuritySurfaceKind(str, Enum):
    AUTHORIZATION = "authorization"
    STATE_TRANSITION = "state_transition"
    OBJECT_BOUNDARY = "object_boundary"
    TRUST_BOUNDARY = "trust_boundary"
    OBSERVATION = "observation"


@dataclass(frozen=True)
class Web2SecuritySurface:
    surface_id: str
    endpoint_id: str
    kind: SecuritySurfaceKind
    priority: int
    question: str
    executable: bool
    blocker: str | None = None


@dataclass(frozen=True)
class Web2Frontier:
    surfaces: tuple[Web2SecuritySurface, ...]
    blocked_branches: tuple[str, ...]

    @property
    def executable(self) -> tuple[Web2SecuritySurface, ...]:
        return tuple(item for item in self.surfaces if item.executable)


_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_AUTH_TERMS = ("auth", "permission", "role", "admin", "owner", "session", "login", "account")
_OBJECT_TERMS = ("{id}", "{uuid}", "{key}", "/id", "resource")


def _kinds(endpoint: Web2EndpointModel) -> set[SecuritySurfaceKind]:
    path = endpoint.path.lower()
    action = (endpoint.action or "").lower()
    kinds: set[SecuritySurfaceKind] = set()
    if endpoint.resource_ids:
        kinds.add(SecuritySurfaceKind.OBJECT_BOUNDARY)
    if endpoint.method.upper() in _MUTATING_METHODS:
        kinds.add(SecuritySurfaceKind.STATE_TRANSITION)
    if any(term in path or term in action for term in _AUTH_TERMS):
        kinds.add(SecuritySurfaceKind.AUTHORIZATION)
    if any(term in path for term in _OBJECT_TERMS):
        kinds.add(SecuritySurfaceKind.TRUST_BOUNDARY)
    return kinds or {SecuritySurfaceKind.OBSERVATION}


def build_web2_security_frontier(
    model: Web2TargetModel,
    *,
    blocked_capabilities: tuple[str, ...] = (),
) -> Web2Frontier:
    """Rank reachable security questions without requiring every capability.

    A capability gap only blocks a surface when that exact surface needs the
    missing capability.  Other executable surfaces remain candidates.
    """
    observed = {item.endpoint_id for item in model.observations}
    surfaces: list[Web2SecuritySurface] = []

    for endpoint in sorted(model.endpoints.values(), key=lambda item: item.endpoint_id):
        kinds = _kinds(endpoint)
        is_observed = endpoint.endpoint_id in observed
        needs_resource = bool(endpoint.resource_ids)
        blocked = "RESOURCE_STATE_ACQUISITION" in blocked_capabilities and needs_resource and not model.resources
        for kind in sorted(kinds, key=lambda value: value.value):
            if kind is SecuritySurfaceKind.AUTHORIZATION:
                question = f"Does {endpoint.method} {endpoint.path} enforce its modeled authorization boundary?"
                priority = 100
            elif kind is SecuritySurfaceKind.STATE_TRANSITION:
                question = f"Does {endpoint.method} {endpoint.path} preserve its security invariant across the state transition?"
                priority = 95
            elif kind is SecuritySurfaceKind.OBJECT_BOUNDARY:
                question = f"Does {endpoint.method} {endpoint.path} enforce ownership/identity separation for the referenced object?"
                priority = 90
            elif kind is SecuritySurfaceKind.TRUST_BOUNDARY:
                question = f"Does {endpoint.method} {endpoint.path} trust attacker-controlled object references safely?"
                priority = 85
            else:
                question = f"What security-relevant behavior can be established from the observed {endpoint.method} {endpoint.path} response?"
                priority = 70
            executable = is_observed and not blocked
            blocker = "RESOURCE_STATE_ACQUISITION" if blocked else None
            surfaces.append(Web2SecuritySurface(
                surface_id=f"surface:{endpoint.endpoint_id}:{kind.value}",
                endpoint_id=endpoint.endpoint_id,
                kind=kind,
                priority=priority,
                question=question,
                executable=executable,
                blocker=blocker,
            ))

    surfaces.sort(key=lambda item: (-item.priority, item.surface_id))
    return Web2Frontier(tuple(surfaces), tuple(sorted(set(blocked_capabilities))))


def branch_local_capability_blocked(frontier: Web2Frontier, capability: str) -> bool:
    """Return whether *all* executable security surfaces depend on capability."""
    relevant = [item for item in frontier.surfaces if item.blocker == capability]
    executable = frontier.executable
    return bool(relevant) and not executable
