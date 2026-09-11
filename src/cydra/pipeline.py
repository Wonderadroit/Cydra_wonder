from __future__ import annotations

from pathlib import Path

from .models import InvestigationResult
from .reasoning import build_evidence, generate_access_control_hypotheses, plan_access_control_experiment, access_control_invariant
from .solidity_model import parse_solidity


def investigate(path: str | Path, target: str | None = None) -> InvestigationResult:
    contracts = parse_solidity(path)
    if not contracts:
        raise ValueError(f"No Solidity contract found in {path}")

    all_invariants = []
    all_hypotheses = []
    all_experiments = []
    all_evidence = []

    for contract in contracts:
        hypotheses = generate_access_control_hypotheses(contract)
        if hypotheses:
            all_invariants.append(access_control_invariant(contract))
        all_hypotheses.extend(hypotheses)
        all_experiments.extend(plan_access_control_experiment(h) for h in hypotheses)
        all_evidence.extend(build_evidence(contract, hypotheses))

    return InvestigationResult(
        target=target or str(path),
        contracts=contracts,
        invariants=tuple(all_invariants),
        hypotheses=tuple(all_hypotheses),
        experiments=tuple(all_experiments),
        evidence=tuple(all_evidence),
    )
