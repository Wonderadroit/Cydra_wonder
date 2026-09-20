from pathlib import Path

from cydra.pipeline import investigate
from cydra.structural_cross_contract_attribution import (
    generate_cross_contract_attribution_hypotheses,
)


def test_legacy_surfaces_do_not_recognize_olympus_attribution_shape():
    root = Path(__file__).resolve().parents[1]
    result = investigate(
        root / "benchmarks/016_olympus_cross_contract_attribution/Target.sol",
        reasoning_surfaces=(),
    )
    assert not result.hypotheses


def test_cross_contract_attribution_surface_recognizes_historical_shape():
    root = Path(__file__).resolve().parents[1]
    result = investigate(
        root / "benchmarks/016_olympus_cross_contract_attribution/Target.sol",
        reasoning_surfaces=(generate_cross_contract_attribution_hypotheses,),
    )
    matches = [
        h
        for h in result.hypotheses
        if h.invariant_id.startswith("INV-CROSS-CONTRACT-ATTRIBUTION-")
    ]
    assert len(matches) == 1
    assert matches[0].target_function == "repayLoan"
