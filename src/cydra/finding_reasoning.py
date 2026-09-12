"""Conservative finding promotion bridge over canonical reasoning evidence."""
from __future__ import annotations

from .finding_gate import FindingCandidate, GateResult, evaluate_finding


def evaluate_candidate(candidate: FindingCandidate) -> GateResult:
    """Apply the basic finding gate; graph-aware promotion remains explicit."""
    return evaluate_finding(candidate)
