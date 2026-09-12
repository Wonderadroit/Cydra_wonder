from __future__ import annotations

from pathlib import Path

from .models import InvestigationResult
from .reasoning import (
    access_control_invariant,
    arithmetic_rounding_invariant,
    build_evidence,
    cached_accounting_invariant,
    generate_access_control_hypotheses,
    generate_arithmetic_hypotheses,
    generate_cached_accounting_hypotheses,
    generate_initialization_hypotheses,
    initialization_invariant,
    plan_access_control_experiment,
    plan_arithmetic_experiment,
    plan_cached_accounting_experiment,
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
        arith = generate_arithmetic_hypotheses(contract)
        accounting = generate_cached_accounting_hypotheses(contract)
        if auth:
            all_invariants.append(access_control_invariant(contract))
        if init:
            all_invariants.append(initialization_invariant(contract))
        arithmetic_invariant = arithmetic_rounding_invariant(contract)
        if arith and arithmetic_invariant is not None:
            all_invariants.append(arithmetic_invariant)
        accounting_invariant = cached_accounting_invariant(contract)
        if accounting and accounting_invariant is not None:
            all_invariants.append(accounting_invariant)
        all_hypotheses.extend((*auth, *init, *arith, *accounting))
        all_experiments.extend(plan_access_control_experiment(h) for h in auth)
        all_experiments.extend(plan_initialization_experiment(h) for h in init)
        all_experiments.extend(plan_arithmetic_experiment(h) for h in arith)
        all_experiments.extend(plan_cached_accounting_experiment(h) for h in accounting)
        all_evidence.extend(build_evidence(contract, (*auth, *init, *arith, *accounting)))
    return InvestigationResult(target=target or str(path), contracts=tuple(contracts), invariants=tuple(all_invariants), hypotheses=tuple(all_hypotheses), experiments=tuple(all_experiments), evidence=tuple(all_evidence))
