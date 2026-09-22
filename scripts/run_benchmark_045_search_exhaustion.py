from __future__ import annotations

from dataclasses import dataclass

from cydra.models import Experiment, Hypothesis, Invariant
from cydra.research_loop import run_research_loop


@dataclass(frozen=True)
class Observation:
    status: str


def main() -> int:
    invariants = (
        Invariant("INV-045-FIRST", "first candidate", "benchmark-045", 0.9),
        Invariant("INV-045-SECOND", "second candidate", "benchmark-045", 0.8),
    )
    hypotheses = (
        Hypothesis("H-045-FIRST", "first executable candidate", "INV-045-FIRST", "first_fn", "caller", "impact"),
        Hypothesis("H-045-SECOND", "second executable candidate", "INV-045-SECOND", "second_fn", "caller", "impact"),
    )
    experiments = (
        Experiment("E-045-FIRST", "H-045-FIRST", "first experiment", ("distinguish",), 1.0),
        Experiment("E-045-SECOND", "H-045-SECOND", "second experiment", ("distinguish",), 1.0),
    )

    seen: list[str] = []

    def execute(hypothesis: Hypothesis, experiment: Experiment) -> Observation:
        seen.append(hypothesis.hypothesis_id)
        return Observation("contradicted")

    result = run_research_loop(
        hypotheses,
        invariants,
        experiments,
        execute=execute,
        status_of=lambda observation: observation.status,
        max_rounds=5,
    )

    assert seen == ["H-045-FIRST", "H-045-SECOND"]
    assert result.termination_reason == "hypothesis_exhausted"
    assert len(result.rounds) == 2

    print({
        "status": "PASS",
        "rounds": len(result.rounds),
        "selected": seen,
        "termination_reason": result.termination_reason,
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
