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
from typing import Literal

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
    budget_used: float = 0.0

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

    def next_question(self, remaining_budget: float) -> ExplorationQuestion | None:
        """Select the highest information-gain-per-cost question within budget."""
        eligible = [
            question
            for question in self.unresolved_questions
            if question.question_id not in self.explored_hypothesis_ids
            and question.estimated_cost <= remaining_budget
        ]
        if not eligible:
            return None
        return max(
            eligible,
            key=lambda question: (
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
                    estimated_cost=1.0,
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
