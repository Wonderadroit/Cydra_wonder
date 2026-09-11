from __future__ import annotations

from pathlib import Path

from .models import InvestigationResult
from .reasoning import (
    access_control_invariant,
    build_evidence,
    generate_access_control_hypotheses,
    generate_initialization_hypotheses,
    initialization_invariant,
    plan_access_control_experiment,
    plan_initialization_experiment,
)
from .solidity_model import parse_solidity


def investigate(path: str | Path, target: str | None = None) -> InvestigationResult:
    contracts = parse_solidity(path)
    if not contracts:
        raise ValueError(f"No Solidity contract found in {path}")
    all_invariants, all_hypotheses, all_experiments, all_evidence = [], [], [], []
    for contract in contracts:
        auth = generate_access_control_hypotheses(contract)
        init = generate_initialization_hypotheses(contract)
        if auth:
            all_invariants.append(access_control_invariant(contract))
        if init:
            all_invariants.append(initialization_invariant(contract))
        all_hypotheses.extend((*auth, *init))
        all_experiments.extend(plan_access_control_experiment(h) for h in auth)
        all_experiments.extend(plan_initialization_experiment(h) for h in init)
        all_evidence.extend(build_evidence(contract, (*auth, *init)))
    return InvestigationResult(target=target or str(path), contracts=contracts, invariants=tuple(all_invariants), hypotheses=tuple(all_hypotheses), experiments=tuple(all_experiments), evidence=tuple(all_evidence))
