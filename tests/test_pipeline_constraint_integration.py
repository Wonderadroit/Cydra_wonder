from pathlib import Path

from cydra.compiler_constraints import ConstraintEvidence
from cydra.models import ContractModel, FunctionModel, Hypothesis, ParameterModel
from cydra.pipeline import investigate


def _contract(tmp_path: Path) -> tuple[Path, ContractModel]:
    source = tmp_path / "Target.sol"
    source.write_text("contract Target {}\n", encoding="utf-8")
    function = FunctionModel(
        name="withdraw",
        visibility="external",
        modifiers=(),
        writes=("balances",),
        external_calls=(),
        line=1,
        parameters=(ParameterModel(name="amount", type="uint256"),),
    )
    return source, ContractModel(name="Target", source=str(source), functions=(function,))


def _withdraw_hypothesis() -> Hypothesis:
    return Hypothesis(
        hypothesis_id="H-AUTH-withdraw",
        claim="withdraw may permit an unauthorized caller to mutate state",
        invariant_id="INV-AUTH-001",
        target_function="withdraw",
        attacker_capability="arbitrary external caller",
        expected_impact="state mutation",
    )


def _patch_pipeline(monkeypatch, contract):
    monkeypatch.setattr("cydra.pipeline.parse_solidity", lambda path: (contract,))
    monkeypatch.setattr("cydra.pipeline.generate_access_control_hypotheses", lambda c: (_withdraw_hypothesis(),))
    monkeypatch.setattr("cydra.pipeline.generate_structural_access_control_hypotheses", lambda c, evidence=(): ())
    monkeypatch.setattr("cydra.pipeline.generate_initialization_hypotheses", lambda c: ())
    monkeypatch.setattr("cydra.pipeline.generate_structural_initialization_hypotheses", lambda c: ())
    monkeypatch.setattr("cydra.pipeline.generate_arithmetic_hypotheses", lambda c: ())


def test_constraints_reach_experiment_planning(monkeypatch, tmp_path: Path):
    source, contract = _contract(tmp_path)
    _patch_pipeline(monkeypatch, contract)

    constraints = (
        ConstraintEvidence(
            contract="Target",
            function="withdraw",
            parameter="amount",
            parameter_index=0,
            predicate="amount > 0",
            source="solc-json-ast:Target.sol",
        ),
    )

    result = investigate(source, constraint_evidence=constraints)

    experiment = result.experiments[0]
    assert experiment.hypothesis_id == "H-AUTH-withdraw"
    assert experiment.planned_inputs == ("1",)


def test_foreign_function_constraint_never_reaches_target_experiment(monkeypatch, tmp_path: Path):
    source, contract = _contract(tmp_path)
    _patch_pipeline(monkeypatch, contract)

    constraints = (
        ConstraintEvidence(
            contract="Target",
            function="deposit",
            parameter="amount",
            parameter_index=0,
            predicate="amount == 0",
            source="solc-json-ast:Target.sol",
        ),
    )

    result = investigate(source, constraint_evidence=constraints)

    # The foreign constraint would select 0 if contamination were present.
    # The target function therefore must retain its generic safe default of 1.
    assert result.experiments[0].planned_inputs == ("1",)
