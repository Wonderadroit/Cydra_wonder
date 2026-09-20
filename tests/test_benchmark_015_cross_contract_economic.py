from pathlib import Path
from cydra.pipeline import investigate
from cydra.structural_cross_contract_economic import generate_cross_contract_economic_hypotheses

def test_existing_extractors_alone_do_not_recognize_mechanism():
    root = Path(__file__).resolve().parents[1]
    result = investigate(root / "benchmarks/015_cross_contract_economic/Target.sol", reasoning_surfaces=())
    assert not result.hypotheses

def test_cross_contract_economic_surface_recognizes_system_invariant():
    root = Path(__file__).resolve().parents[1]
    result = investigate(
        root / "benchmarks/015_cross_contract_economic/Target.sol",
        reasoning_surfaces=(generate_cross_contract_economic_hypotheses,),
    )
    contributions = [generate_cross_contract_economic_hypotheses(c) for c in result.contracts]
    assert any(c.hypotheses for c in contributions), [(c.name, len(c.functions)) for c in result.contracts]
    matches = [h for h in result.hypotheses if h.invariant_id.startswith("INV-CROSS-CONTRACT-ECONOMIC-")]
    assert len(matches) == 1
    assert matches[0].target_function == "syncStrategy"
