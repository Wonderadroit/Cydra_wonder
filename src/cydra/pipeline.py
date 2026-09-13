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
    plan_arithmetic_experiment,
    plan_initialization_experiment,
)
from .solidity_model import parse_solidity
from .structural_arithmetic import arithmetic_rounding_invariant, generate_arithmetic_hypotheses
from .structural_authorization import generate_structural_access_control_hypotheses
from .structural_initialization import generate_structural_initialization_hypotheses


def _merge_hypotheses(*groups):
    merged = {}
    for group in groups:
        for hypothesis in group:
            merged[hypothesis.hypothesis_id] = hypothesis
    return tuple(merged.values())


def investigate(path: str | Path, target: str | None = None) -> InvestigationResult:
    contracts = parse_solidity(path)
    if not contracts:
        raise ValueError(f"No Solidity contract found in {path}")
    all_invariants, all_hypotheses, all_experiments, all_evidence = [], [], [], []
    for contract in contracts:
        auth = _merge_hypotheses(
            generate_access_control_hypotheses(contract),
            generate_structural_access_control_hypotheses(contract),
        )
        init = _merge_hypotheses(
            generate_initialization_hypotheses(contract),
            generate_structural_initialization_hypotheses(contract),
        )
        arith = generate_arithmetic_hypotheses(contract)
        if auth:
            all_invariants.append(access_control_invariant(contract))
        if init:
            all_invariants.append(initialization_invariant(contract))
        arithmetic_invariant = arithmetic_rounding_invariant(contract)
        if arith and arithmetic_invariant is not None:
            all_invariants.append(arithmetic_invariant)
        all_hypotheses.extend((*auth, *init, *arith))
        all_experiments.extend(plan_access_control_experiment(h) for h in auth)
        all_experiments.extend(plan_initialization_experiment(h) for h in init)
        all_experiments.extend(plan_arithmetic_experiment(h) for h in arith)
        all_evidence.extend(build_evidence(contract, (*auth, *init, *arith)))
    return InvestigationResult(target=target or str(path), contracts=tuple(contracts), invariants=tuple(all_invariants), hypotheses=tuple(all_hypotheses), experiments=tuple(all_experiments), evidence=tuple(all_evidence))
