from dataclasses import dataclass

from cydra.models import Experiment, Hypothesis, Invariant
from cydra.research_loop import run_research_loop


@dataclass(frozen=True)
class Observation:
    status: str


@dataclass(frozen=True)
class Finding:
    finding_id: str


def main() -> None:
    hypotheses = (
        Hypothesis("H-048-A", "first", "INV-048-A", "first", "caller", "impact"),
        Hypothesis("H-048-B", "second", "INV-048-B", "second", "caller", "impact"),
    )
    invariants = (
        Invariant("INV-048-A", "first", "benchmark", 1.0),
        Invariant("INV-048-B", "second", "benchmark", 1.0),
    )
    experiments = (
        Experiment("E-048-A", "H-048-A", "first", ("d",), 1.0),
        Experiment("E-048-B", "H-048-B", "second", ("d",), 1.0),
    )
    finding = Finding("F-048-repeat")
    result = run_research_loop(
        hypotheses,
        invariants,
        experiments,
        execute=lambda h, e: Observation("confirmed"),
        status_of=lambda o: o.status,
        finding_of=lambda o: finding,
        finding_target="benchmark-048",
        max_rounds=2,
    )
    assert result.findings is not None
    assert result.findings.findings == (finding,)
    print("Benchmark 048: PASS")
    print("rounds=2")
    print("retained_findings=1")


if __name__ == "__main__":
    main()
