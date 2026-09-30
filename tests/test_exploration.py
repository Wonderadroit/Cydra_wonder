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


def test_canonical_execution_bridge_scopes_one_question_and_preserves_full_result(monkeypatch, tmp_path):
    from scripts import run_benchmark_blind
    from cydra.exploration import select_next_question

    result = _result()
    state = ExplorationState.from_investigation(result)
    decision = select_next_question(state, 2.0)
    assert decision is not None

    observed = {}

    def fake_run_layers(scoped, project, classes, compiler_evidence):
        observed["hypotheses"] = tuple(item.hypothesis_id for item in scoped.hypotheses)
        observed["experiments"] = tuple(item.experiment_id for item in scoped.experiments)
        return (
            [{
                "hypothesis_id": "H-1",
                "class": "authorization",
                "classification": "NOT_REACHED",
            }],
            [],
            (Evidence("E-BRIDGE", "execution", "bridge executed", "test"),),
        )

    monkeypatch.setattr(run_benchmark_blind, "run_layers", fake_run_layers)
    trace = []
    executions = []
    evidence = []

    updated, returned_evidence = run_benchmark_blind._execute_exploration_question(
        result,
        decision,
        tmp_path,
        ("authorization",),
        None,
        trace,
        executions,
        evidence,
    )

    assert observed == {"hypotheses": ("H-1",), "experiments": ("X-1",)}
    assert tuple(item.hypothesis_id for item in updated.hypotheses) == ("H-1",)
    assert tuple(item.hypothesis_id for item in result.hypotheses) == ("H-1",)
    assert [item.evidence_id for item in returned_evidence] == ["E-BRIDGE"]
    assert trace[0]["question_id"] == "Q-HYP-H-1"
    assert evidence[0].evidence_id == "E-BRIDGE"


def test_controller_does_not_charge_non_executable_questions_to_experiment_budget():
    from cydra.exploration import run_bounded_exploration

    run = run_bounded_exploration(
        _result(),
        budget=2.0,
        executable_hypothesis_ids=frozenset(),
        execute_question=lambda *_: (_result(), ()),
    )

    assert run.rounds == 0
    assert run.state.budget_used == 0.0
    assert run.stopped_reason == "no_executable_hypotheses"
    assert "Q-HYP-H-1" in run.state.capability_work_items
    assert "Q-FN-Target.observe" in run.state.capability_work_items
    assert "Q-STATE-Target.value" in run.state.capability_work_items


def test_controller_charges_only_adapter_backed_hypotheses():
    from cydra.exploration import run_bounded_exploration

    calls = []

    def execute(result, decision):
        calls.append(decision.question_id)
        evidence = Evidence(f"E-{len(calls)}", "execution", "attempted", "test")
        return result, (evidence,)

    run = run_bounded_exploration(
        _result(),
        budget=2.0,
        executable_hypothesis_ids=frozenset({"H-1"}),
        execute_question=execute,
    )

    assert calls == ["Q-HYP-H-1"]
    assert run.rounds == 1
    assert run.state.budget_used == 2.0
