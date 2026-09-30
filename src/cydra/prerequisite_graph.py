from __future__ import annotations

from dataclasses import dataclass, replace

from .execution_readiness import ExecutionReadiness, SetupAction


@dataclass(frozen=True)
class PrerequisiteNode:
    """Evidence-backed prerequisite; discovery never implies verification."""

    subject: str
    kind: str
    status: str
    source: str
    dependencies: tuple[str, ...] = ()
    transition: str | None = None
    verification: str | None = None
    capability: str | None = None


@dataclass(frozen=True)
class PrerequisiteGraph:
    """Immutable target-neutral prerequisite graph for one experiment."""

    nodes: tuple[PrerequisiteNode, ...] = ()

    @property
    def verified(self) -> tuple[PrerequisiteNode, ...]:
        return tuple(node for node in self.nodes if node.status == "verified")

    @property
    def unresolved(self) -> tuple[PrerequisiteNode, ...]:
        return tuple(
            node for node in self.nodes if node.status in {"unresolved", "blocked"}
        )

    def by_subject(self, subject: str) -> tuple[PrerequisiteNode, ...]:
        return tuple(node for node in self.nodes if node.subject == subject)

    @property
    def capability_clusters(self) -> dict[str, int]:
        """Count unresolved prerequisites by generic execution capability."""
        counts: dict[str, int] = {}
        for node in self.unresolved:
            capability = node.capability or "EXECUTION_READINESS"
            counts[capability] = counts.get(capability, 0) + 1
        return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _capability_for_requirement(kind: str) -> str:
    """Map readiness evidence to a stable execution capability name."""
    mapping = {
        "caller_role": "CALLER_CONSTRUCTION",
        "caller_state_dependency": "STATE_SETUP",
        "caller_state_setup_candidate": "STATE_SETUP",
        "execution_state_dependency": "STATE_OBSERVATION",
        "state_dependency": "STATE_OBSERVATION",
        "constructor_dependency": "CONSTRUCTOR_SETUP",
        "runtime_dependency": "INTERNAL_CALL_PROPAGATION",
        "internal_execution_dependency": "INTERNAL_CALL_PROPAGATION",
    }
    if kind in mapping:
        return mapping[kind]
    if "state" in kind:
        return "STATE_OBSERVATION"
    if "constructor" in kind:
        return "CONSTRUCTOR_SETUP"
    if "caller" in kind or "role" in kind:
        return "CALLER_CONSTRUCTION"
    return "EXECUTION_READINESS"


def build_prerequisite_graph(
    readiness: ExecutionReadiness,
    setup_actions: tuple[SetupAction, ...] = (),
) -> PrerequisiteGraph:
    """Normalize readiness without falsely promoting execution to verification."""

    nodes: list[PrerequisiteNode] = []
    requirements = (
        *readiness.constructor_requirements,
        *readiness.caller_requirements,
        *readiness.runtime_requirements,
        *readiness.state_requirements,
        *readiness.execution_requirements,
    )
    for item in requirements:
        status = {
            "required": "unresolved",
            "discovered": "unresolved",
            "constructible": "constructible",
            "verified": "verified",
            "constraint": "constraint",
        }.get(item.status, "unresolved")
        nodes.append(
            PrerequisiteNode(
                subject=item.subject,
                kind=item.kind,
                status=status,
                source=item.source,
                verification="runtime_observation_required",
                capability=_capability_for_requirement(item.kind),
            )
        )

    for action in setup_actions:
        nodes.append(
            PrerequisiteNode(
                subject=action.function,
                kind="setup_transition",
                status="constructible",
                source="execution_readiness",
                transition=action.function,
                verification="postcondition_required",
                capability="STATE_SETUP",
            )
        )

    unique: dict[tuple[str, str, str], PrerequisiteNode] = {}
    for node in nodes:
        unique[(node.kind, node.subject, node.source)] = node
    return PrerequisiteGraph(tuple(unique.values()))


def can_enter_security_experiment(graph: PrerequisiteGraph) -> bool:
    """Require every prerequisite to be explicitly verified.

    A constructible setup action is not enough. This is deliberately fail-closed
    so execution success cannot be mistaken for state satisfaction.
    """

    return not graph.unresolved and all(
        node.status in {"verified", "constraint"} for node in graph.nodes
    )


@dataclass(frozen=True)
class PrerequisiteObservation:
    """Deterministic runtime observation used to promote one prerequisite."""
    kind: str
    subject: str
    expected: str
    observed: str
    evidence_id: str


def apply_observations(
    graph: PrerequisiteGraph,
    observations: tuple[PrerequisiteObservation, ...],
) -> PrerequisiteGraph:
    """Promote only evidence-backed matching prerequisites; fail closed otherwise."""
    by_subject = {(observation.kind, observation.subject): observation for observation in observations}
    nodes: list[PrerequisiteNode] = []
    for node in graph.nodes:
        observation = by_subject.get((node.kind, node.subject))
        if observation is None:
            nodes.append(node)
            continue
        if not observation.evidence_id:
            nodes.append(
                replace(node, status="unresolved", verification="missing_evidence_id")
            )
            continue
        if observation.expected == observation.observed:
            nodes.append(
                replace(node, status="verified", verification=observation.evidence_id)
            )
        else:
            nodes.append(
                replace(node, status="blocked", verification=observation.evidence_id)
            )
    return PrerequisiteGraph(tuple(nodes))
