from __future__ import annotations

from dataclasses import dataclass, replace
import re

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


def _capability_for_requirement(kind: str, category: str | None = None) -> str:
    """Map readiness evidence to a stable execution capability name."""
    category_mapping = {
        "cryptographic_witness": "CRYPTOGRAPHIC_WITNESS",
        "execution_context": "EXECUTION_CONTEXT",
        "state_observation": "STATE_OBSERVATION",
        "local_execution": "LOCAL_EXECUTION",
        "input_construction": "INPUT_CONSTRUCTION",
    }
    if category in category_mapping:
        return category_mapping[category]

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
                capability=_capability_for_requirement(item.kind, item.category),
            )
        )

    state_subjects = {item.subject for item in readiness.state_requirements}
    for action in setup_actions:
        provenance_state = action.provenance[-1] if action.provenance else None
        dependencies = tuple(
            subject
            for subject in state_subjects
            if provenance_state
            and re.search(
                rf"(?<![A-Za-z0-9_]){re.escape(provenance_state)}(?![A-Za-z0-9_])",
                subject,
            )
        )
        nodes.append(
            PrerequisiteNode(
                subject=action.function,
                kind="setup_transition",
                status="constructible",
                source="execution_readiness",
                dependencies=dependencies,
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
    """Require every security-critical prerequisite to be verified.

    Constructible state/setup prerequisites remain fail-closed: merely knowing
    that a fixture *can* be built must never be treated as proof that target
    state is established. Runtime dependencies owned by the execution adapter
    are different: their construction is part of the target call itself and
    does not need a separate pre-experiment observation. The capability label
    makes that distinction explicit without introducing target-specific logic.
    """

    if graph.unresolved:
        return False

    allowed_constructible_capabilities = {
        "INTERNAL_CALL_PROPAGATION",
    }
    return all(
        node.status in {"verified", "constraint"}
        or (
            node.status == "constructible"
            and node.capability in allowed_constructible_capabilities
        )
        for node in graph.nodes
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
    state_requirement_kinds = {
        "state_predicate",
        "state_dependency",
        "execution_state_dependency",
    }
    nodes: list[PrerequisiteNode] = []
    for node in graph.nodes:
        observation = None
        if node.kind in state_requirement_kinds:
            observation = next(
                (
                    item for item in observations
                    if item.kind == "state" and item.subject == node.subject
                ),
                None,
            )
        else:
            observation = next(
                (
                    item for item in observations
                    if item.kind == node.kind and item.subject == node.subject
                ),
                None,
            )

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

    verified_state_subjects = {
        node.subject
        for node in nodes
        if node.kind in state_requirement_kinds and node.status == "verified"
    }
    for index, node in enumerate(nodes):
        if node.kind != "setup_transition" or node.status != "constructible":
            continue
        matching_dependency = next(
            (dependency for dependency in node.dependencies if dependency in verified_state_subjects),
            None,
        )
        if matching_dependency is None:
            continue
        evidence = next(
            (
                item for item in observations
                if item.kind == "state" and item.subject == matching_dependency
            ),
            None,
        )
        if evidence is not None and evidence.evidence_id:
            nodes[index] = replace(
                node,
                status="verified",
                verification=evidence.evidence_id,
            )

    return PrerequisiteGraph(tuple(nodes))
