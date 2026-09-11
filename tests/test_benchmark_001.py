from pathlib import Path

from cydra.pipeline import investigate


FIXTURE = Path(__file__).parents[1] / "benchmarks/alchemix_missing_access_control/Target.sol"


def test_benchmark_001_builds_system_model_and_hypothesis():
    result = investigate(FIXTURE, target="benchmark-001/alchemix-missing-access-control")

    assert {c.name for c in result.contracts} == {"AlchemixAccessControlFixture"}
    functions = {f.name: f for f in result.contracts[0].functions}
    assert {"setGovernance", "setWhitelist"}.issubset(functions)
    assert "onlyGov" in functions["setGovernance"].modifiers
    assert functions["setWhitelist"].modifiers == ()

    assert result.invariants[0].invariant_id == "INV-AUTH-001"
    assert [h.hypothesis_id for h in result.hypotheses] == ["H-AUTH-setWhitelist"]
    assert result.experiments[0].hypothesis_id == "H-AUTH-setWhitelist"
    assert "unprivileged actor" in result.experiments[0].action

    evidence = {e.evidence_id: e for e in result.evidence}
    assert "E-MODEL-setWhitelist" in evidence
    assert evidence["E-MODEL-setWhitelist"].location is not None
