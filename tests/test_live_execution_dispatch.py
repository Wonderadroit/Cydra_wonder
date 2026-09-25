from cydra.models import Experiment, Hypothesis
from scripts.run_benchmark_blind import _execution_adapter, _unknown_reasoning_status


def test_live_runner_uses_one_capability_dispatch_boundary():
    assert _execution_adapter("authorization").__name__ == "_run_authorization"
    assert _execution_adapter("state").__name__ == "_run_state"
    assert _execution_adapter("initialization").__name__ == "_run_initialization"
    assert _execution_adapter("guard_parity").__name__ == "_run_guard_parity"
    assert _execution_adapter("external_outcome") is None


def test_planned_unknown_surface_is_recorded_as_an_execution_gap():
    hypothesis = Hypothesis(
        hypothesis_id="H-EXTERNAL-OUTCOME-target",
        claim="external operation failure may not stop the transition",
        invariant_id="INV-EXTERNAL-OUTCOME-target",
        target_function="target",
        attacker_capability="caller-controlled callee",
        expected_impact="state transition continues after reported failure",
    )
    experiment = Experiment(
        experiment_id="X-H-EXTERNAL-OUTCOME-target",
        hypothesis_id=hypothesis.hypothesis_id,
        action="exercise external failure",
        discriminates=("stops", "continues"),
        cost=1.0,
        target_function="target",
    )

    status = _unknown_reasoning_status(hypothesis, experiment)

    assert status["class"] == "reasoning_surface"
    assert status["execution_capability"] == "UNIMPLEMENTED"
    assert status["blind_executed"] is False
    assert status["classification"] == "NOT_REACHED"
