from __future__ import annotations

from pathlib import Path
from collections.abc import Iterable

from .ast_dataflow import SemanticRelationshipEvidence
from .compiler_constraints import ConstraintEvidence
from .experiment_inputs import plan_parameter_inputs
from .experiment_planning import bind_experiment
from .models import Experiment, InvestigationResult
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


def _attach_input_plan(
    contract,
    hypothesis,
    experiment: Experiment,
    constraints: tuple[ConstraintEvidence, ...],
) -> Experiment:
    function = next((item for item in contract.functions if item.name == hypothesis.target_function), None)
    if function is None:
        return experiment
    vector = plan_parameter_inputs(
        function.parameters,
        constraints,
        function_name=function.name,
    )
    return bind_experiment(
        hypothesis,
        experiment,
        target_function=function.name,
        planned_inputs=vector,
    )


def investigate(
    path: str | Path,
    target: str | None = None,
    semantic_evidence: Iterable[SemanticRelationshipEvidence] | None = None,
    constraint_evidence: Iterable[ConstraintEvidence] | None = None,
) -> InvestigationResult:
    """Build an investigation from compiler-backed evidence and class-neutral reasoning.

    Parameter constraints are optional evidence. When a complete safe ABI vector can
    be constructed, it is attached to the experiment; otherwise the empty vector
    explicitly preserves the existing generator fallback. Constraint interpretation
    remains independent of vulnerability class and invariant.
    """
    contracts = parse_solidity(path)
    if not contracts:
        raise ValueError(f"No Solidity contract found in {path}")

    semantic = tuple(semantic_evidence or ())
    constraints = tuple(constraint_evidence or ())
    all_invariants, all_hypotheses, all_experiments, all_evidence = [], [], [], []
    for contract in contracts:
        contract_semantic = tuple(item for item in semantic if item.contract == contract.name)
        contract_constraints = tuple(item for item in constraints if item.contract == contract.name)
        if contract_semantic:
            structural_auth = generate_structural_access_control_hypotheses(contract, contract_semantic)
            # Compiler coverage is evidence, not an instruction to disable another
            # reasoning path. Structural and lexical detectors are independent
            # witnesses and are merged/deduplicated by hypothesis identity.
            lexical_auth = generate_access_control_hypotheses(contract)
            auth = _merge_hypotheses(structural_auth, lexical_auth)
        else:
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

        hypotheses = (*auth, *init, *arith)
        all_hypotheses.extend(hypotheses)
        for hypothesis in auth:
            all_experiments.append(_attach_input_plan(contract, hypothesis, plan_access_control_experiment(hypothesis), contract_constraints))
        for hypothesis in init:
            all_experiments.append(_attach_input_plan(contract, hypothesis, plan_initialization_experiment(hypothesis), contract_constraints))
        for hypothesis in arith:
            all_experiments.append(_attach_input_plan(contract, hypothesis, plan_arithmetic_experiment(hypothesis), contract_constraints))
        all_evidence.extend(build_evidence(contract, hypotheses))

    return InvestigationResult(
        target=target or str(path),
        contracts=tuple(contracts),
        invariants=tuple(all_invariants),
        hypotheses=tuple(all_hypotheses),
        experiments=tuple(all_experiments),
        evidence=tuple(all_evidence),
    )
