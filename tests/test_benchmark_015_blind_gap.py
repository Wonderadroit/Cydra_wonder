from pathlib import Path
from cydra.pipeline import investigate

def test_existing_extractors_do_not_recognize_cross_contract_economic_mechanism():
    root = Path(__file__).resolve().parents[1]
    result = investigate(root / "benchmarks/015_cross_contract_economic/Target.sol")
    assert not result.hypotheses
