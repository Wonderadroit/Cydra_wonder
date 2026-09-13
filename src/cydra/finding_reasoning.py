"""Conservative finding promotion bridge."""
from __future__ import annotations
from .finding_gate import FindingCandidate, GateResult, evaluate_finding

def evaluate_candidate(candidate: FindingCandidate) -> GateResult:
    return evaluate_finding(candidate)
