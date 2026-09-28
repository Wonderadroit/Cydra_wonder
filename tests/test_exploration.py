from __future__ import annotations

from cydra.exploration import ExplorationState, derive_exploration_frontier
from cydra.models import ContractModel, Evidence, Experiment, FunctionModel, Hypothesis, InvestigationResult, Invariant


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


def test_frontier_does_not_reselect_explored_hypothesis():
    state = ExplorationState.from_investigation(_result())
    state = ExplorationState(
        **{
            **state.__dict__,
            "explored_hypothesis_ids": ("H-1",),
        }
    )

    question = state.next_question(remaining_budget=2.0)

    assert question is not None
    assert question.hypothesis_id != "H-1"


def test_controller_records_attempt_and_updates_budget():
    from cydra.exploration import record_exploration_step, select_next_question
    state = ExplorationState.from_investigation(_result())
    decision = select_next_question(state, 2.0)
    assert decision is not None
    advanced = record_exploration_step(state, decision, evidence_ids=("E-BLOCKED",))
    assert advanced.explored_question_ids == ("Q-HYP-H-1",)
    assert advanced.explored_hypothesis_ids == ("H-1",)
    assert advanced.evidence_ids == ("E-BLOCKED",)
    assert advanced.budget_used == 2.0

def test_frontier_refresh_preserves_exploration_history():
    from cydra.exploration import record_exploration_step, refresh_exploration_frontier, select_next_question
    state = ExplorationState.from_investigation(_result())
    decision = select_next_question(state, 2.0)
    assert decision is not None
    advanced = record_exploration_step(state, decision)
    refreshed = refresh_exploration_frontier(_result(), advanced)
    assert refreshed.explored_hypothesis_ids == ("H-1",)
    assert all(q.question_id != "Q-HYP-H-1" for q in refreshed.unresolved_questions)
    assert refreshed.budget_used == 2.0


def test_execution_evidence_is_attached_to_selected_hypothesis():
    from cydra.exploration import apply_exploration_evidence, select_next_question
    state = ExplorationState.from_investigation(_result())
    decision = select_next_question(state, 2.0)
    assert decision is not None
    evidence = Evidence("E-EXEC-H-1", "execution", "execution attempted", "foundry")
    updated = apply_exploration_evidence(_result(), decision, (evidence,))
    hypothesis = next(item for item in updated.hypotheses if item.hypothesis_id == "H-1")
    assert hypothesis.evidence_ids == ("E-EXEC-H-1",)
    assert updated.evidence == (evidence,)


def test_bounded_controller_reenters_frontier_after_feedback():
    from cydra.exploration import run_bounded_exploration
    calls = []

    def execute(result, decision):
        calls.append(decision.question_id)
        evidence = Evidence(f"E-{len(calls)}", "execution", "attempted", "test")
        return result, (evidence,)

    run = run_bounded_exploration(_result(), budget=4.0, execute_question=execute)

    assert run.rounds == 2
    assert run.state.budget_used == 4.0
    assert calls == ["Q-HYP-H-1", "Q-FN-Target.observe"]
    assert run.stopped_reason == "budget_exhausted"
