from __future__ import annotations

from dataclasses import dataclass

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
        }.get(item.status, "unresolved")
        nodes.append(
            PrerequisiteNode(
                subject=item.subject,
                kind=item.kind,
                status=status,
                source=item.source,
                verification="runtime_observation_required",
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
        node.status == "verified" for node in graph.nodes
    )


@dataclass(frozen=True)
class PrerequisiteObservation:
    """Deterministic runtime observation used to promote one prerequisite."""
    subject: str
    expected: str
    observed: str
    evidence_id: str


def apply_observations(
    graph: PrerequisiteGraph,
    observations: tuple[PrerequisiteObservation, ...],
) -> PrerequisiteGraph:
    """Promote only evidence-backed matching prerequisites; fail closed otherwise."""
    by_subject = {observation.subject: observation for observation in observations}
    nodes: list[PrerequisiteNode] = []
    for node in graph.nodes:
        observation = by_subject.get(node.subject)
        if observation is None:
            nodes.append(node)
            continue
        if not observation.evidence_id:
            nodes.append(
                PrerequisiteNode(**{**node.__dict__, "status": "unresolved", "verification": "missing_evidence_id"})
            )
            continue
        if observation.expected == observation.observed:
            nodes.append(
                PrerequisiteNode(**{**node.__dict__, "status": "verified", "verification": observation.evidence_id})
            )
        else:
            nodes.append(
                PrerequisiteNode(**{**node.__dict__, "status": "blocked", "verification": observation.evidence_id})
            )
    return PrerequisiteGraph(tuple(nodes))
