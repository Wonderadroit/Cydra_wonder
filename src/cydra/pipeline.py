from __future__ import annotations

from pathlib import Path
from collections.abc import Callable, Iterable
import inspect
from dataclasses import replace

from .ast_dataflow import SemanticRelationshipEvidence
from .compiler_constraints import ConstraintEvidence
from .experiment_inputs import plan_parameter_inputs
from .experiment_planning import bind_experiment, plan_experiment
from .models import ContractModel, Experiment, ExperimentStep, Hypothesis, InvestigationResult, Invariant
from .reasoning import (
    access_control_invariant,
    build_evidence,
    generate_access_control_hypotheses,
    generate_initialization_hypotheses,
    initialization_invariant,
    plan_access_control_experiment,
    plan_arithmetic_experiment,
    plan_initialization_experiment,
    plan_weighted_average_rounding_experiment,
    plan_guard_parity_experiment,
    plan_temporal_precondition_experiment,
    plan_idempotency_experiment,
    plan_read_only_reentrancy_experiment,
    plan_transfer_accounting_experiment,
    plan_redemption_rounding_experiment,
    plan_cross_contract_economic_experiment,
    plan_cross_contract_attribution_experiment,
)
from .solidity_model import parse_solidity
from .structural_arithmetic import arithmetic_rounding_invariant, generate_arithmetic_hypotheses
from .structural_pair_symmetry import paired_subtraction_invariant, generate_pair_symmetry_hypotheses
from .structural_aggregation_order import aggregation_order_invariant, generate_aggregation_order_hypotheses
from .structural_configuration_binding import configuration_binding_invariant, generate_configuration_binding_hypotheses
from .configuration_binding_planning import plan_configuration_binding_experiment
from .structural_rounding import weighted_average_rounding_invariant, generate_weighted_average_rounding_hypotheses
from .structural_authorization import generate_structural_access_control_hypotheses
from .structural_initialization import generate_structural_initialization_hypotheses
from .structural_guard_parity import generate_guard_parity_hypotheses
from .structural_idempotency import generate_idempotency_hypotheses
from .structural_read_only_reentrancy import generate_read_only_reentrancy_hypotheses, generate_cross_contract_read_only_reentrancy_hypotheses
from .structural_transfer_accounting import generate_transfer_accounting_hypotheses
from .structural_redemption_rounding import generate_redemption_rounding_hypotheses
from .structural_cross_contract_economic import generate_cross_contract_economic_hypotheses
from .structural_cross_contract_attribution import generate_cross_contract_attribution_hypotheses
from .structural_control_flow import generate_control_flow_hypotheses
from .structural_signature_reuse import generate_signature_reuse_hypotheses
from .structural_signed_metadata import generate_signed_metadata_hypotheses
from .structural_intent_parity import generate_intent_parity_hypotheses
from .intent_parity_planning import plan_intent_parity_experiment
from .signature_reuse_planning import plan_signature_reuse_experiment
from .signature_replay_planning import plan_signature_replay_experiment
from .signed_metadata_planning import plan_signed_metadata_experiment
from .control_flow_planning import plan_control_flow_experiment
from .structural_epoch_accounting import generate_epoch_accounting_hypotheses
from .epoch_accounting_planning import plan_epoch_accounting_experiment
from .structural_external_outcome import generate_external_outcome_hypotheses
from .external_outcome_planning import plan_external_outcome_experiment
from .structural_type_domain import generate_type_domain_hypotheses
from .type_domain_planning import plan_type_domain_experiment
from .structural_resource_authorization import generate_resource_authorization_hypotheses
from .resource_authorization_planning import plan_resource_authorization_experiment
from .structural_callback_state_order import generate_callback_state_order_hypotheses
from .structural_incentive_liveness import generate_incentive_liveness_hypotheses
from .structural_unbounded_iteration import generate_unbounded_iteration_hypotheses
from .unbounded_iteration_planning import plan_unbounded_iteration_experiment
from .incentive_liveness_planning import plan_incentive_liveness_experiment
from .callback_state_order_planning import plan_callback_state_order_experiment
from .state_experiments import plan_cross_function_state_experiment
from .reasoning_surface import ReasoningContribution
from .structural_state import generate_cross_function_state_hypotheses
from .structural_temporal import generate_temporal_precondition_hypotheses
from .structural_signature_replay import generate_signature_replay_hypotheses
from .structural_double_debit import generate_double_debit_hypotheses
from .structural_storage_persistence import generate_storage_persistence_hypotheses


ReasoningSurface = Callable[..., ReasoningContribution]


def _merge_hypotheses(*groups):
    merged = {}
    for group in groups:
        for hypothesis in group:
            merged[hypothesis.hypothesis_id] = hypothesis
    return tuple(merged.values())


def _default_experiment_planner(hypothesis: Hypothesis) -> Experiment:
    """Adapt today's reasoning surfaces to the class-neutral experiment envelope.

    This is the legacy/class-specific adapter, deliberately kept outside the core
    pipeline. New reasoning surfaces may supply their own planner without adding a
    branch to investigate().
    """
    planners = {
        "INV-AUTH-001": plan_access_control_experiment,
        "INV-INIT-001": plan_initialization_experiment,
        "INV-ARITH-001": plan_arithmetic_experiment,
        "INV-PAIR-SYMMETRY-001": plan_arithmetic_experiment,
        "INV-AGGREGATION-ORDER-001": plan_arithmetic_experiment,
        "INV-CONFIG-BINDING-001": plan_configuration_binding_experiment,
        "INV-ROUND-001": plan_weighted_average_rounding_experiment,
    }
    if hypothesis.invariant_id.startswith("INV-CONTROL-FLOW-"):
        return plan_control_flow_experiment(hypothesis)
    if hypothesis.invariant_id.startswith("INV-GUARD-PARITY-"):
        return plan_guard_parity_experiment(hypothesis)
    if hypothesis.invariant_id.startswith("INV-TEMPORAL-PRECONDITION-"):
        return plan_temporal_precondition_experiment(hypothesis)
    if hypothesis.invariant_id.startswith("INV-IDEMPOTENCY-"):
        return plan_idempotency_experiment(hypothesis)
    if hypothesis.invariant_id.startswith(("INV-READONLY-REENTRANCY-", "INV-READONLY-XCONTRACT-")):
        return plan_read_only_reentrancy_experiment(hypothesis)
    if hypothesis.invariant_id.startswith("INV-TRANSFER-ACCOUNTING-"):
        return plan_transfer_accounting_experiment(hypothesis)
    if hypothesis.invariant_id.startswith("INV-REDEMPTION-ROUNDING-"):
        return plan_redemption_rounding_experiment(hypothesis)
    if hypothesis.invariant_id.startswith("INV-CROSS-CONTRACT-ECONOMIC-"):
        return plan_cross_contract_economic_experiment(hypothesis)
    if hypothesis.invariant_id.startswith("INV-CROSS-CONTRACT-ATTRIBUTION-"):
        return plan_cross_contract_attribution_experiment(hypothesis)
    if hypothesis.invariant_id.startswith("INV-SIGNATURE-REUSE-"):
        return plan_signature_reuse_experiment(hypothesis)
    if hypothesis.invariant_id.startswith("INV-SIGNED-METADATA-"):
        return plan_signed_metadata_experiment(hypothesis)
    if hypothesis.invariant_id.startswith("INV-INTENT-PARITY-"):
        return plan_intent_parity_experiment(hypothesis)
    if hypothesis.invariant_id.startswith("INV-EPOCH-ACCOUNTING-"):
        return plan_epoch_accounting_experiment(hypothesis)
    if hypothesis.invariant_id.startswith("INV-EXTERNAL-OUTCOME-"):
        return plan_external_outcome_experiment(hypothesis)
    if hypothesis.invariant_id.startswith("INV-TYPE-DOMAIN-"):
        return plan_type_domain_experiment(hypothesis)
    if hypothesis.invariant_id.startswith("INV-RESOURCE-AUTH-"):
        return plan_resource_authorization_experiment(hypothesis)
    if hypothesis.invariant_id.startswith("INV-CALLBACK-STATE-ORDER-"):
        return plan_callback_state_order_experiment(hypothesis)
    if hypothesis.invariant_id.startswith("INV-INCENTIVE-LIVENESS-"):
        return plan_incentive_liveness_experiment(hypothesis)
    if hypothesis.invariant_id.startswith("INV-UNBOUNDED-ITERATION-"):
        return plan_unbounded_iteration_experiment(hypothesis)
    if hypothesis.invariant_id.startswith("INV-STATE-"):
        return plan_cross_function_state_experiment(hypothesis)
    if hypothesis.invariant_id.startswith("INV-TEMPORAL-PRECONDITION-"):
        return plan_temporal_precondition_experiment(hypothesis)
    if hypothesis.invariant_id.startswith("INV-SIGNATURE-REPLAY-"):
        return plan_signature_replay_experiment(hypothesis)
    if hypothesis.invariant_id.startswith(("INV-DOUBLE-DEBIT-", "INV-STORAGE-PERSISTENCE-")):
        return plan_experiment(
            hypothesis,
            action="construct a transaction that traces the suspected value/state transition and compare persistent accounting before and after the operation",
            discriminates=(
                "the modeled state transition persists exactly once",
                "the caller bears an additional value/state transition not reflected by the modeled accounting",
            ),
            cost=1.0,
        )
    try:
        planner = planners[hypothesis.invariant_id]
    except KeyError as exc:
        raise ValueError(
            f"no default experiment planner for invariant {hypothesis.invariant_id}"
        ) from exc
    return planner(hypothesis)


def _attach_input_plan(
    contract,
    hypothesis,
    experiment: Experiment,
    constraints: tuple[ConstraintEvidence, ...],
) -> Experiment:
    """Attach complete ABI argument vectors to the experiment and its sequence steps.

    The same generic input-planning capability must serve both single-call and
    ordered experiments. A sequence planner may identify a causally relevant peer
    with only a placeholder argument; the orchestration boundary resolves that
    placeholder against the peer function's actual parameter model. No invariant
    class or benchmark-specific knowledge is used here.
    """
    function = next((item for item in contract.functions if item.name == hypothesis.target_function), None)
    bound = experiment
    if function is not None:
        vector = experiment.planned_inputs or plan_parameter_inputs(
            function.parameters,
            constraints,
            function_name=function.name,
        )
        bound = bind_experiment(
            hypothesis,
            experiment,
            target_function=function.name,
            planned_inputs=vector,
        )

    if not bound.steps:
        return bound

    functions = {item.name: item for item in contract.functions}
    planned_steps: list[ExperimentStep] = []
    for step in bound.steps:
        step_function = functions.get(step.function)
        if step_function is None:
            planned_steps.append(step)
            continue
        vector = plan_parameter_inputs(
            step_function.parameters,
            constraints,
            function_name=step_function.name,
        )
        # An empty vector is the explicit "not safely planned" signal from the
        # generic planner. Preserve the existing step so the renderer fails closed
        # rather than inventing ABI values for custom/unknown types.
        arguments = vector if vector or not step_function.parameters else ()
        planned_steps.append(replace(step, arguments=arguments))

    return replace(bound, steps=tuple(planned_steps))


def investigate(
    path: str | Path,
    target: str | None = None,
    semantic_evidence: Iterable[SemanticRelationshipEvidence] | None = None,
    constraint_evidence: Iterable[ConstraintEvidence] | None = None,
    experiment_planner: Callable[[Hypothesis], Experiment] | None = None,
    reasoning_surfaces: Iterable[ReasoningSurface] | None = None,
    system_model=None,
) -> InvestigationResult:
    """Build an investigation while keeping experiment transport class-neutral.

    Reasoning adapters discover hypotheses and may plan class-specific experiments.
    The pipeline only transports those plans through generic binding and execution
    preparation. A caller can inject a planner for a new reasoning surface without
    changing this orchestration layer.
    """
    contracts = parse_solidity(path)
    if not contracts:
        raise ValueError(f"No Solidity contract found in {path}")

    planner = experiment_planner or _default_experiment_planner
    surfaces = tuple(reasoning_surfaces) if reasoning_surfaces is not None else (generate_cross_contract_economic_hypotheses, generate_cross_contract_attribution_hypotheses, generate_cross_contract_read_only_reentrancy_hypotheses, generate_control_flow_hypotheses, generate_epoch_accounting_hypotheses, generate_external_outcome_hypotheses, generate_type_domain_hypotheses, generate_resource_authorization_hypotheses, generate_callback_state_order_hypotheses, generate_incentive_liveness_hypotheses, generate_unbounded_iteration_hypotheses, generate_cross_function_state_hypotheses, generate_temporal_precondition_hypotheses, generate_signature_replay_hypotheses, generate_double_debit_hypotheses, generate_storage_persistence_hypotheses,)
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
        pair_symmetry = generate_pair_symmetry_hypotheses(contract)
        aggregation_order = generate_aggregation_order_hypotheses(contract)
        configuration_binding = generate_configuration_binding_hypotheses(contract)
        rounding = generate_weighted_average_rounding_hypotheses(contract)
        guard_parity = generate_guard_parity_hypotheses(contract, contract_semantic)
        idempotency = generate_idempotency_hypotheses(contract, contract_semantic)
        readonly = generate_read_only_reentrancy_hypotheses(contract, contract_semantic)
        transfer_accounting = generate_transfer_accounting_hypotheses(contract, contract_semantic)
        redemption_rounding = generate_redemption_rounding_hypotheses(contract, contract_semantic)
        signature_reuse = generate_signature_reuse_hypotheses(contract, contract_semantic)
        signed_metadata = generate_signed_metadata_hypotheses(contract, contract_semantic)
        intent_invariants, intent_hypotheses = generate_intent_parity_hypotheses(contract, contract_semantic)
        type_domain = generate_type_domain_hypotheses(contract, contract_semantic)
        resource_auth = generate_resource_authorization_hypotheses(contract, contract_semantic)
        unbounded_iteration = generate_unbounded_iteration_hypotheses(contract, contract_semantic)

        if auth:
            all_invariants.append(access_control_invariant(contract))
        if init:
            all_invariants.append(initialization_invariant(contract))
        arithmetic_invariant = arithmetic_rounding_invariant(contract)
        if arith and arithmetic_invariant is not None:
            all_invariants.append(arithmetic_invariant)
        pair_symmetry_invariant = paired_subtraction_invariant(contract)
        if pair_symmetry and pair_symmetry_invariant is not None:
            all_invariants.append(pair_symmetry_invariant)
        aggregation_order_invariant_result = aggregation_order_invariant(contract)
        if aggregation_order and aggregation_order_invariant_result is not None:
            all_invariants.append(aggregation_order_invariant_result)
        configuration_binding_invariant_result = configuration_binding_invariant(contract)
        if configuration_binding and configuration_binding_invariant_result is not None:
            all_invariants.append(configuration_binding_invariant_result)
        rounding_invariant = weighted_average_rounding_invariant(contract)
        if rounding and rounding_invariant is not None:
            all_invariants.append(rounding_invariant)

        surface_invariants: list[Invariant] = []
        surface_hypotheses: list[Hypothesis] = []
        for surface in surfaces:
            # Repository-aware surfaces may consume the canonical SystemModel.
            # Legacy surfaces remain two-argument adapters. The graph is context,
            # not a finding: explicit hypotheses still require executable evidence.
            parameters = inspect.signature(surface).parameters
            if system_model is not None and len(parameters) >= 3:
                contribution = surface(contract, contract_semantic, system_model)
            else:
                contribution = surface(contract, contract_semantic)
            surface_invariants.extend(contribution.invariants)
            surface_hypotheses.extend(contribution.hypotheses)

        hypotheses = _merge_hypotheses(
            auth,
            init,
            arith,
            pair_symmetry,
            aggregation_order,
            configuration_binding,
            rounding,
            guard_parity.hypotheses,
            idempotency.hypotheses,
            readonly.hypotheses,
            transfer_accounting.hypotheses,
            redemption_rounding.hypotheses,
            signature_reuse.hypotheses,
            signed_metadata.hypotheses,
            intent_hypotheses,
            type_domain.hypotheses,
            resource_auth.hypotheses,
            unbounded_iteration,
            surface_hypotheses,
        )
        all_invariants.extend(guard_parity.invariants)
        all_invariants.extend(idempotency.invariants)
        all_invariants.extend(readonly.invariants)
        all_invariants.extend(transfer_accounting.invariants)
        all_invariants.extend(redemption_rounding.invariants)
        all_invariants.extend(signature_reuse.invariants)
        all_invariants.extend(signed_metadata.invariants)
        all_invariants.extend(intent_invariants)
        all_invariants.extend(type_domain.invariants)
        all_invariants.extend(resource_auth.invariants)
        all_invariants.extend(unbounded_iteration.invariants)
        all_invariants.extend(surface_invariants)
        all_hypotheses.extend(hypotheses)
        for hypothesis in hypotheses:
            experiment = planner(hypothesis)
            all_experiments.append(
                _attach_input_plan(contract, hypothesis, experiment, contract_constraints)
            )
        all_evidence.extend(build_evidence(contract, hypotheses))

    return InvestigationResult(
        target=target or str(path),
        contracts=tuple(contracts),
        invariants=tuple(all_invariants),
        hypotheses=tuple(all_hypotheses),
        experiments=tuple(all_experiments),
        evidence=tuple(all_evidence),
    )
