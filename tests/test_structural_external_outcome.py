from pathlib import Path

from cydra.pipeline import investigate


def test_external_outcome_reasoning_is_class_neutral():
    source = Path("benchmarks/029_external_outcome/Withdrawer.sol")
    result = investigate(source)
    matches = [h for h in result.hypotheses if h.invariant_id.startswith("INV-EXTERNAL-OUTCOME-")]
    assert any(h.target_function == "withdraw" for h in matches)
