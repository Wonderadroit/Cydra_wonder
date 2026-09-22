from __future__ import annotations

from dataclasses import dataclass

from cydra.models import Experiment, Hypothesis, Invariant
from cydra.research_loop import run_research_loop


@dataclass(frozen=True)
class Observation:
    status: str


def main() -> int:
    invariants = (
        Invariant("INV-046-A", "candidate A", "benchmark-046", 0.95),
        Invariant("INV-046-B", "candidate B", "benchmark-046", 0.85),
    )
    hypotheses = (
        Hypothesis("H-046-A", "candidate A", "INV-046-A", "a", "caller", "impact"),
        Hypothesis("H-046-B", "candidate B", "INV-046-B", "b", "caller", "impact"),
    )
    experiments = (
        Experiment("E-046-A", "H-046-A", "A cannot be rendered safely", ("execution",), 1.0),
        Experiment("E-046-B", "H-046-B", "B is executable", ("execution",), 1.0),
    )

    seen: list[str] = []

    def execute(hypothesis: Hypothesis, experiment: Experiment) -> Observation:
        seen.append(hypothesis.hypothesis_id)
        if hypothesis.hypothesis_id == "H-046-A":
            return Observation("UNMEASURABLE")
        return Observation("confirmed")

    result = run_research_loop(
        hypotheses,
        invariants,
        experiments,
        execute=execute,
        status_of=lambda o: o.status,
        stop_when=lambda o: o.status == "confirmed",
        max_rounds=3,
    )

    assert seen == ["H-046-A", "H-046-B"]
    assert [r.status for r in result.rounds] == ["UNMEASURABLE", "confirmed"]
    assert result.termination_reason == "stop_condition"

    print({
        "status": "PASS",
        "selected": seen,
        "statuses": [r.status for r in result.rounds],
        "termination_reason": result.termination_reason,
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
