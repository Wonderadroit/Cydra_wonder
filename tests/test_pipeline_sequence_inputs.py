from pathlib import Path

from cydra.compiler_constraints import ConstraintEvidence
from cydra.models import ContractModel, Experiment, ExperimentStep, FunctionModel, Hypothesis, ParameterModel, Invariant
from cydra.pipeline import ReasoningContribution, investigate


def test_sequence_steps_receive_generic_abi_vectors(monkeypatch, tmp_path: Path):
    source = tmp_path / "Target.sol"
    source.write_text("contract Target {}\n", encoding="utf-8")
    contract = ContractModel(
        name="Target",
        source=str(source),
        functions=(
            FunctionModel(
                "prepare", "external", (), ("state",), (), 1,
                (ParameterModel("token", "address"), ParameterModel("amount", "uint256")),
            ),
            FunctionModel(
                "consume", "external", (), ("state",), (), 2,
                (ParameterModel("token", "address"), ParameterModel("amount", "uint256")),
            ),
        ),
    )
    hypothesis = Hypothesis(
        "H-STATE-state-consume",
        "consume may violate modeled state consistency after prepare",
        "INV-STATE-state",
        "consume",
        "arbitrary external caller",
        "inconsistent state",
        related_functions=("prepare",),
    )

    monkeypatch.setattr("cydra.pipeline.parse_solidity", lambda path: (contract,))
    monkeypatch.setattr(
        "cydra.pipeline.generate_access_control_hypotheses",
        lambda c: (),
    )
    monkeypatch.setattr(
        "cydra.pipeline.generate_structural_access_control_hypotheses",
        lambda c, evidence=(): (),
    )
    monkeypatch.setattr("cydra.pipeline.generate_initialization_hypotheses", lambda c: ())
    monkeypatch.setattr("cydra.pipeline.generate_structural_initialization_hypotheses", lambda c: ())
    monkeypatch.setattr("cydra.pipeline.generate_arithmetic_hypotheses", lambda c: ())

    def state_surface(c, evidence=()):
        return ReasoningContribution(
            invariants=(Invariant("INV-STATE-state", "state consistency", "test", 0.6),),
            hypotheses=(hypothesis,),
        )

    def planner(h):
        return Experiment(
            "X-H-STATE-state-consume",
            h.hypothesis_id,
            "prepare then consume",
            ("violation", "preservation"),
            2.0,
            steps=(
                ExperimentStep("prepare", ("1",)),
                ExperimentStep("consume", ("1",)),
            ),
        )

    result = investigate(
        source,
        semantic_evidence=(),
        experiment_planner=planner,
        reasoning_surfaces=(state_surface,),
        constraint_evidence=(),
    )

    experiment = result.experiments[0]
    assert experiment.steps == (
        ExperimentStep("prepare", ("address(0xCAFE)", "1")),
        ExperimentStep("consume", ("address(0xCAFE)", "1")),
    )


def test_sequence_step_constraints_are_bound_to_each_function(monkeypatch, tmp_path: Path):
    source = tmp_path / "Target.sol"
    source.write_text("contract Target {}\n", encoding="utf-8")
    contract = ContractModel(
        name="Target",
        source=str(source),
        functions=(
            FunctionModel(
                "prepare", "external", (), ("state",), (), 1,
                (ParameterModel("amount", "uint256"), ParameterModel("recipient", "address")),
            ),
            FunctionModel(
                "consume", "external", (), ("state",), (), 2,
                (ParameterModel("amount", "uint256"), ParameterModel("recipient", "address")),
            ),
        ),
    )
    hypothesis = Hypothesis(
        "H-STATE-state-consume", "candidate", "INV-STATE-state", "consume",
        "arbitrary external caller", "impact", related_functions=("prepare",),
    )

    monkeypatch.setattr("cydra.pipeline.parse_solidity", lambda path: (contract,))
    monkeypatch.setattr("cydra.pipeline.generate_access_control_hypotheses", lambda c: ())
    monkeypatch.setattr("cydra.pipeline.generate_structural_access_control_hypotheses", lambda c, evidence=(): ())
    monkeypatch.setattr("cydra.pipeline.generate_initialization_hypotheses", lambda c: ())
    monkeypatch.setattr("cydra.pipeline.generate_structural_initialization_hypotheses", lambda c: ())
    monkeypatch.setattr("cydra.pipeline.generate_arithmetic_hypotheses", lambda c: ())

    def state_surface(c, evidence=()):
        return ReasoningContribution((
            Invariant("INV-STATE-state", "state consistency", "test", 0.6),
        ), (hypothesis,))

    def planner(h):
        return Experiment(
            "X-H-STATE-state-consume", h.hypothesis_id, "prepare then consume",
            ("violation", "preservation"), 2.0,
            steps=(ExperimentStep("prepare", ("1", "address(0xCAFE)")),
                   ExperimentStep("consume", ("1", "address(0xCAFE)"))),
        )

    constraints = (
        ConstraintEvidence("Target", "prepare", "amount", 0, "amount > 7", "prepare constraint"),
        ConstraintEvidence("Target", "consume", "amount", 0, "amount == 9", "consume constraint"),
    )

    result = investigate(
        source, experiment_planner=planner, reasoning_surfaces=(state_surface,),
        constraint_evidence=constraints,
    )

    assert result.experiments[0].steps == (
        ExperimentStep("prepare", ("1", "address(0xCAFE)")),
        ExperimentStep("consume", ("9", "address(0xCAFE)")),
    )
