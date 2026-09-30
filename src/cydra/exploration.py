from __future__ import annotations

"""Generic target-exploration state and frontier selection.

This module does not discover vulnerabilities and does not execute experiments.
It turns the existing investigation result into a bounded, persistent frontier
of questions that the execution/reasoning layers can consume.

The design deliberately stays class-neutral: a question describes uncertainty
about the target model or an unvalidated hypothesis, rather than naming a
vulnerability class.
"""

from dataclasses import dataclass, field
from typing import Callable, Literal

from .models import Experiment, Hypothesis, InvestigationResult

QuestionKind = Literal["hypothesis", "function_surface", "state_surface"]


@dataclass(frozen=True)
class ExplorationQuestion:
    question_id: str
    kind: QuestionKind
    subject: str
    prompt: str
    uncertainty: float
    estimated_information_gain: float
    estimated_cost: float
    hypothesis_id: str | None = None
    target_function: str | None = None


@dataclass(frozen=True)
class ExplorationState:
    """Durable, serializable view of what the investigation knows and does not know."""

    target: str
    contracts: tuple[str, ...]
    functions: tuple[str, ...]
    state_surfaces: tuple[str, ...]
    hypotheses: tuple[Hypothesis, ...] = field(default_factory=tuple)
    experiments: tuple[Experiment, ...] = field(default_factory=tuple)
    evidence_ids: tuple[str, ...] = field(default_factory=tuple)
    unresolved_questions: tuple[ExplorationQuestion, ...] = field(default_factory=tuple)
    explored_hypothesis_ids: tuple[str, ...] = field(default_factory=tuple)
    explored_question_ids: tuple[str, ...] = field(default_factory=tuple)
    budget_used: float = 0.0
    capability_work_items: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_investigation(cls, result: InvestigationResult) -> "ExplorationState":
        contracts = tuple(contract.name for contract in result.contracts)
        functions = tuple(
            f"{contract.name}.{function.name}"
            for contract in result.contracts
            for function in contract.functions
        )
        state_surfaces = tuple(
            f"{contract.name}.{state}"
            for contract in result.contracts
            for state in contract.state_variables
        )
        questions = derive_exploration_frontier(result)
        return cls(
            target=result.target,
            contracts=contracts,
            functions=functions,
            state_surfaces=state_surfaces,
            hypotheses=result.hypotheses,
            experiments=result.experiments,
            evidence_ids=tuple(evidence.evidence_id for evidence in result.evidence),
            unresolved_questions=questions,
        )

    def next_question(self, remaining_budget: float, executable_hypothesis_ids: frozenset[str] | None = None) -> ExplorationQuestion | None:
        """Select an executable hypothesis question without charging capability work to experiment budget."""
        eligible = [
            question
            for question in self.unresolved_questions
            if question.question_id not in self.explored_question_ids
            and question.estimated_cost <= remaining_budget
            and (
                (
                    executable_hypothesis_ids is None
                    and (
                        question.hypothesis_id is None
                        or question.hypothesis_id not in self.explored_hypothesis_ids
                    )
                )
                or (
                    executable_hypothesis_ids is not None
                    and question.hypothesis_id is not None
                    and question.hypothesis_id not in self.explored_hypothesis_ids
                    and question.hypothesis_id in executable_hypothesis_ids
                )
            )
        ]
        if not eligible:
            return None
        candidates = eligible
        # Hypothesis questions already have a discriminating experiment and
        # therefore take precedence over uncovered model-surface questions.
        # Capability/frontier questions are still retained, but are consumed
        # only after the executable hypothesis frontier is exhausted.
        return max(
            candidates,
            key=lambda question: (
                1 if question.hypothesis_id is not None else 0,
                question.estimated_information_gain / max(question.estimated_cost, 0.01),
                question.estimated_information_gain,
                question.uncertainty,
                question.question_id,
            ),
        )


def derive_exploration_frontier(result: InvestigationResult) -> tuple[ExplorationQuestion, ...]:
    """Derive generic next questions from the current model and evidence.

    Proposed hypotheses are preferred because they already have a discriminating
    experiment. Functions and state surfaces without any hypothesis coverage remain
    explicit exploration questions instead of being silently ignored.
    """
    questions: list[ExplorationQuestion] = []
    hypothesis_functions: set[str] = set()

    for hypothesis in result.hypotheses:
        hypothesis_functions.add(hypothesis.target_function)
        if hypothesis.status != "proposed":
            continue
        experiment = next(
            (item for item in result.experiments if item.hypothesis_id == hypothesis.hypothesis_id),
            None,
        )
        if experiment is None:
            continue
        cost = max(float(experiment.cost), 0.01)
        evidence_count = len(hypothesis.evidence_ids)
        uncertainty = max(0.1, 1.0 - min(evidence_count, 4) * 0.15)
        questions.append(
            ExplorationQuestion(
                question_id=f"Q-HYP-{hypothesis.hypothesis_id}",
                kind="hypothesis",
                subject=hypothesis.hypothesis_id,
                prompt=(
                    f"What evidence most efficiently distinguishes the current "
                    f"hypothesis {hypothesis.hypothesis_id} from its alternatives?"
                ),
                uncertainty=uncertainty,
                estimated_information_gain=min(1.0, 0.7 + 0.1 * len(hypothesis.related_functions)),
                estimated_cost=cost,
                hypothesis_id=hypothesis.hypothesis_id,
                target_function=hypothesis.target_function,
            )
        )

    for contract in result.contracts:
        for function in contract.functions:
            qualified = f"{contract.name}.{function.name}"
            if qualified in hypothesis_functions:
                continue
            questions.append(
                ExplorationQuestion(
                    question_id=f"Q-FN-{qualified}",
                    kind="function_surface",
                    subject=qualified,
                    prompt=(
                        f"What system behavior, state transition, authorization boundary, "
                        f"or dependency remains unknown around {qualified}?"
                    ),
                    uncertainty=0.8,
                    estimated_information_gain=0.6,
                    estimated_cost=2.0,
                    target_function=function.name,
                )
            )

        for state in contract.state_variables:
            qualified = f"{contract.name}.{state}"
            questions.append(
                ExplorationQuestion(
                    question_id=f"Q-STATE-{qualified}",
                    kind="state_surface",
                    subject=qualified,
                    prompt=(
                        f"What evidence establishes how {qualified} is initialized, "
                        f"read, written, and constrained across reachable transitions?"
                    ),
                    uncertainty=0.7,
                    estimated_information_gain=0.5,
                    estimated_cost=1.0,
                )
            )

    return tuple(
        sorted(
            questions,
            key=lambda question: (
                -(question.estimated_information_gain / max(question.estimated_cost, 0.01)),
                -question.uncertainty,
                question.question_id,
            ),
        )
    )


@dataclass(frozen=True)
class ExplorationDecision:
    """One bounded frontier selection made by the exploration controller."""
    question_id: str
    hypothesis_id: str | None
    target_function: str | None
    estimated_cost: float


def select_next_question(state: ExplorationState, remaining_budget: float, executable_hypothesis_ids: frozenset[str] | None = None) -> ExplorationDecision | None:
    """Select an executable frontier question without executing or inventing any experiment."""
    question = state.next_question(remaining_budget, executable_hypothesis_ids)
    if question is None:
        return None
    return ExplorationDecision(question.question_id, question.hypothesis_id, question.target_function, question.estimated_cost)


def record_exploration_step(state: ExplorationState, decision: ExplorationDecision, *, evidence_ids: tuple[str, ...] = (), actual_cost: float | None = None) -> ExplorationState:
    """Record an attempted question; execution remains owned by the existing pipeline."""
    cost = decision.estimated_cost if actual_cost is None else max(float(actual_cost), 0.0)
    explored_questions = tuple(dict.fromkeys((*state.explored_question_ids, decision.question_id)))
    explored_hypotheses = state.explored_hypothesis_ids
    if decision.hypothesis_id is not None:
        explored_hypotheses = tuple(dict.fromkeys((*explored_hypotheses, decision.hypothesis_id)))
    evidence = tuple(dict.fromkeys((*state.evidence_ids, *evidence_ids)))
    return ExplorationState(
        target=state.target, contracts=state.contracts, functions=state.functions,
        state_surfaces=state.state_surfaces, hypotheses=state.hypotheses,
        experiments=state.experiments, evidence_ids=evidence,
        unresolved_questions=tuple(q for q in state.unresolved_questions if q.question_id != decision.question_id),
        explored_hypothesis_ids=explored_hypotheses, explored_question_ids=explored_questions,
        budget_used=state.budget_used + cost,
        capability_work_items=state.capability_work_items,
    )


def refresh_exploration_frontier(result: InvestigationResult, previous: ExplorationState | None = None) -> ExplorationState:
    """Rebuild the frontier from the latest model while preserving exploration history."""
    current = ExplorationState.from_investigation(result)
    if previous is None:
        return current
    return ExplorationState(
        target=current.target, contracts=current.contracts, functions=current.functions,
        state_surfaces=current.state_surfaces, hypotheses=current.hypotheses,
        experiments=current.experiments,
        evidence_ids=tuple(dict.fromkeys((*previous.evidence_ids, *current.evidence_ids))),
        unresolved_questions=tuple(q for q in current.unresolved_questions
            if q.question_id not in previous.explored_question_ids
            and (q.hypothesis_id is None or q.hypothesis_id not in previous.explored_hypothesis_ids)),
        explored_hypothesis_ids=previous.explored_hypothesis_ids,
        explored_question_ids=previous.explored_question_ids,
        budget_used=previous.budget_used,
        capability_work_items=previous.capability_work_items,
    )


def apply_exploration_evidence(
    result: InvestigationResult,
    decision: ExplorationDecision,
    evidence: tuple["Evidence", ...],
) -> InvestigationResult:
    """Attach execution evidence to the selected hypothesis without interpreting it.

    Interpretation remains owned by the existing causal/hypothesis-update machinery.
    This bridge only preserves provenance so a refreshed frontier can see that the
    selected question has produced new evidence.
    """
    from dataclasses import replace
    by_id = {item.evidence_id: item for item in result.evidence}
    for item in evidence:
        by_id[item.evidence_id] = item

    hypotheses = result.hypotheses
    if decision.hypothesis_id is not None:
        ids = tuple(item.evidence_id for item in evidence)
        hypotheses = tuple(
            replace(
                hypothesis,
                evidence_ids=tuple(dict.fromkeys((*hypothesis.evidence_ids, *ids))),
            )
            if hypothesis.hypothesis_id == decision.hypothesis_id
            else hypothesis
            for hypothesis in hypotheses
        )

    return replace(
        result,
        hypotheses=hypotheses,
        evidence=tuple(by_id.values()),
    )


@dataclass(frozen=True)
class ExplorationRun:
    state: ExplorationState
    result: InvestigationResult
    rounds: int
    stopped_reason: str


def run_bounded_exploration(
    result: InvestigationResult,
    *,
    budget: float,
    execute_question: Callable[[InvestigationResult, ExplorationDecision], tuple[InvestigationResult, tuple["Evidence", ...]]],
    executable_hypothesis_ids: frozenset[str] | None = None,
) -> ExplorationRun:
    """Drive bounded frontier feedback through the existing execution boundary.

    The callback is injected: the exploration layer chooses questions, while the
    canonical runner owns readiness, generation, execution, classification, and
    causal verification. No second executor is introduced.
    """
    state = ExplorationState.from_investigation(result)
    if executable_hypothesis_ids is not None:
        capability_items = tuple(
            question.question_id
            for question in state.unresolved_questions
            if question.hypothesis_id is None
            or question.hypothesis_id not in executable_hypothesis_ids
        )
        state = ExplorationState(
            target=state.target,
            contracts=state.contracts,
            functions=state.functions,
            state_surfaces=state.state_surfaces,
            hypotheses=state.hypotheses,
            experiments=state.experiments,
            evidence_ids=state.evidence_ids,
            unresolved_questions=state.unresolved_questions,
            explored_hypothesis_ids=state.explored_hypothesis_ids,
            explored_question_ids=state.explored_question_ids,
            budget_used=state.budget_used,
            capability_work_items=capability_items,
        )
    rounds = 0
    while state.budget_used < budget:
        remaining = budget - state.budget_used
        decision = select_next_question(state, remaining, executable_hypothesis_ids)
        if decision is None:
            reason = "no_executable_hypotheses" if executable_hypothesis_ids is not None else "frontier_exhausted_or_budget_insufficient"
            return ExplorationRun(state, result, rounds, reason)
        updated_result, evidence = execute_question(result, decision)
        result = apply_exploration_evidence(updated_result, decision, evidence)
        state = record_exploration_step(
            state,
            decision,
            evidence_ids=tuple(item.evidence_id for item in evidence),
        )
        state = refresh_exploration_frontier(result, state)
        rounds += 1
    return ExplorationRun(state, result, rounds, "budget_exhausted")
