from __future__ import annotations

from dataclasses import dataclass

import pytest

from cydra.models import Experiment, Hypothesis, Invariant
from cydra.research_loop import run_research_loop


@dataclass(frozen=True)
class Observation:
    status: str


def _fixtures():
    first_invariant = Invariant("INV-FIRST", "first invariant", "unit-test", 0.9)
    second_invariant = Invariant("INV-SECOND", "second invariant", "unit-test", 0.8)
    first = Hypothesis("H-FIRST", "first", "INV-FIRST", "first_fn", "caller", "impact")
    second = Hypothesis("H-SECOND", "second", "INV-SECOND", "second_fn", "caller", "impact")
    experiments = (
        Experiment("E-FIRST", "H-FIRST", "first experiment", ("distinguish",), 1.0),
        Experiment("E-SECOND", "H-SECOND", "second experiment", ("distinguish",), 1.0),
    )
    return (first, second), (first_invariant, second_invariant), experiments


def test_research_loop_reselects_after_non_terminal_observation():
    hypotheses, invariants, experiments = _fixtures()
    seen = []

    def execute(hypothesis, experiment):
        seen.append(hypothesis.hypothesis_id)
        return Observation("proposed")

    result = run_research_loop(
        hypotheses,
        invariants,
        experiments,
        execute=execute,
        status_of=lambda o: o.status,
        max_rounds=2,
    )

    assert seen == ["H-FIRST", "H-SECOND"]
    assert [r.selection.hypothesis.hypothesis_id for r in result.rounds] == [
        "H-FIRST",
        "H-SECOND",
    ]


def test_research_loop_stops_when_executor_observation_says_to_stop():
    hypotheses, invariants, experiments = _fixtures()
    result = run_research_loop(
        hypotheses,
        invariants,
        experiments,
        execute=lambda h, e: Observation("confirmed"),
        status_of=lambda o: o.status,
        stop_when=lambda o: o.status == "confirmed",
        max_rounds=3,
    )

    assert len(result.rounds) == 1


def test_research_loop_rejects_invalid_round_limit():
    hypotheses, invariants, experiments = _fixtures()
    with pytest.raises(ValueError, match="max_rounds"):
        run_research_loop(
            hypotheses,
            invariants,
            experiments,
            execute=lambda h, e: Observation("proposed"),
            status_of=lambda o: o.status,
            max_rounds=0,
        )


def test_research_loop_fails_closed_on_empty_status():
    hypotheses, invariants, experiments = _fixtures()
    with pytest.raises(ValueError, match="status"):
        run_research_loop(
            hypotheses,
            invariants,
            experiments,
            execute=lambda h, e: Observation(""),
            status_of=lambda o: o.status,
        )
