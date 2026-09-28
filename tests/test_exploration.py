from __future__ import annotations

from cydra.exploration import ExplorationState, derive_exploration_frontier
from cydra.models import ContractModel, Experiment, FunctionModel, Hypothesis, InvestigationResult, Invariant


def _result() -> InvestigationResult:
    function = FunctionModel(
        name="mutate",
        visibility="external",
        modifiers=(),
        writes=("value",),
        external_calls=(),
        line=1,
    )
    untouched = FunctionModel(
        name="observe",
        visibility="external",
        modifiers=(),
        writes=(),
        external_calls=(),
        line=5,
    )
    contract = ContractModel(
        name="Target",
        source="Target.sol",
        functions=(function, untouched),
        state_variables=("value", "other"),
    )
    hypothesis = Hypothesis(
        hypothesis_id="H-1",
        claim="mutate may violate the observed invariant",
        invariant_id="INV-TEST-1",
        target_function="mutate",
        attacker_capability="external caller",
        expected_impact="state transition",
    )
    experiment = Experiment(
        experiment_id="X-1",
        hypothesis_id="H-1",
        action="execute mutate",
        discriminates=("violation", "safe behavior"),
        cost=2.0,
    )
    return InvestigationResult(
        target="Target.sol",
        contracts=(contract,),
        invariants=(Invariant("INV-TEST-1", "value remains valid", "test", 1.0),),
        hypotheses=(hypothesis,),
        experiments=(experiment,),
        evidence=(),
    )


def test_frontier_prefers_testable_hypothesis():
    state = ExplorationState.from_investigation(_result())

    question = state.next_question(remaining_budget=2.0)

    assert question is not None
    assert question.hypothesis_id == "H-1"
    assert question.kind == "hypothesis"


def test_frontier_keeps_uncovered_model_surfaces_explicit():
    questions = derive_exploration_frontier(_result())

    ids = {question.question_id for question in questions}

    assert "Q-FN-Target.observe" in ids
    assert "Q-STATE-Target.value" in ids
    assert "Q-STATE-Target.other" in ids


def test_frontier_is_budget_bounded():
    state = ExplorationState.from_investigation(_result())

    assert state.next_question(remaining_budget=0.5) is None
