from cydra.models import Hypothesis
from cydra.pipeline import _merge_hypotheses


def test_pipeline_deduplicates_same_hypothesis_from_built_in_and_injected_surface():
    hypothesis = Hypothesis(
        "H-DUP-001",
        "same claim",
        "INV-DUP-001",
        "target",
        "actor",
        "impact",
    )

    merged = _merge_hypotheses((hypothesis,), (hypothesis,))

    assert merged == (hypothesis,)
