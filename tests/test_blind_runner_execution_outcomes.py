from pathlib import Path

import scripts.run_benchmark_blind as runner
from cydra.foundry import ExecutionResult
from cydra.models import ContractModel, Experiment, FunctionModel, Hypothesis, ParameterModel


def test_initialization_unmeasurable_execution_is_preserved(monkeypatch, tmp_path: Path):
    hypothesis = Hypothesis(
        "H-INIT-fixture",
        "initialization candidate",
        "INV-INIT-001",
        "initialize",
        "external caller",
        "initialization boundary",
    )
    experiment = Experiment("X-H-INIT-fixture", hypothesis.hypothesis_id, "call", ("violation",), 1.0)
    contract = ContractModel(
        "Fixture",
        str(tmp_path / "Fixture.sol"),
        (FunctionModel("initialize", "external", (), (), (), 4, (ParameterModel("x", "uint256"),)),),
    )
    execution = ExecutionResult(
        experiment.experiment_id,
        "blind",
        ("forge", "test"),
        1,
        False,
        0,
        0,
        "UNMEASURABLE",
        "",
        "constructor precondition could not be established",
    )

    monkeypatch.setattr(runner, "generate_initialization_test", lambda *args, **kwargs: tmp_path / "generated.t.sol")
    monkeypatch.setattr(runner, "run_foundry_test", lambda *args, **kwargs: execution)
    monkeypatch.setattr(
        runner,
        "classify_initialization_execution",
        lambda hypothesis, execution: type(
            "Outcome",
            (),
            {"benchmark_status": "proposed", "internal_status": "proposed", "evidence": None},
        )(),
    )

    result = runner._run_initialization(tmp_path, hypothesis, experiment, contract)

    assert result["execution_status"] == "UNMEASURABLE"
    assert result["execution_executed"] is False
    assert result["tests_run"] == 0
    assert result["tests_failed"] == 0
    assert result["classification"] == "proposed"
