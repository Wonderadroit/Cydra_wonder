from cydra.execution_capabilities import (
    Capability, CapabilityStatus,
    build_experiment_contract, capability_clusters, solve_capabilities,
)
from cydra.execution_readiness import ExecutionReadiness, ExecutionRequirement
from cydra.models import ContractModel, Experiment, FunctionModel, Hypothesis, ParameterModel

def _model():
    function = FunctionModel(
        name='transact', visibility='external', modifiers=(), writes=(),
        external_calls=(), line=1, parameters=(ParameterModel('circomData', 'CircomData', 'calldata'),),
        state_predicates=('externalActionMap[circomData.id] == circomData.address',),
    )
    return ContractModel('Target', '/tmp/Target.sol', (function,))

def _hypothesis():
    return Hypothesis(
        'H-1', 'a callback can observe state before an update', 'INV-CALLBACK-1',
        'transact', 'reentrant callback caller', 'UNKNOWN'
    )

def test_experiment_contract_names_generic_requirements():
    readiness = ExecutionReadiness(
        contract='Target',
        caller_requirements=(ExecutionRequirement('caller_role','attacker','model'),),
        state_requirements=(ExecutionRequirement('state','externalActionMap','model'),),
        runtime_requirements=(ExecutionRequirement('internal','helper','model'),),
    )
    experiment = Experiment('X-1','H-1','transact',('before','after'),2.0,('0',), 'transact')
    contract = build_experiment_contract(_hypothesis(), experiment, _model(), readiness)
    names = {item.capability for item in contract.requirements}
    assert Capability.CALLER_CONSTRUCTION in names
    assert Capability.STATE_SETUP in names
    assert Capability.STATE_OBSERVATION in names
    assert Capability.INTERNAL_CALL_PROPAGATION in names
    assert Capability.TYPE_MATERIALIZATION in names
    assert Capability.CALLBACK_HARNESS in names
    assert any(item.subcapability == 'custom_struct' for item in contract.requirements)

def test_solver_keeps_partial_capability_explicit_and_clusters_it():
    readiness = ExecutionReadiness(
        contract='Target',
        state_requirements=(ExecutionRequirement('state','externalActionMap','model'),),
    )
    experiment = Experiment('X-1','H-1','transact',('before','after'),2.0,(), 'transact')
    resolution = solve_capabilities(build_experiment_contract(_hypothesis(), experiment, _model(), readiness))
    assert not resolution.executable
    assert any(g.capability == Capability.STATE_SETUP and g.status == CapabilityStatus.PARTIAL for g in resolution.gaps)
    assert capability_clusters((resolution,))['STATE_SETUP'] == 1

def test_missing_registry_capability_is_fail_closed():
    readiness = ExecutionReadiness(contract='Target')
    experiment = Experiment('X-1','H-1','transact',('before','after'),2.0,(), 'transact')
    contract = build_experiment_contract(_hypothesis(), experiment, _model(), readiness)
    availability = tuple(item for item in solve_capabilities(contract).availability if item.capability != Capability.TYPE_MATERIALIZATION)
    resolution = solve_capabilities(contract, availability)
    assert any(g.status == CapabilityStatus.MISSING and g.capability == Capability.TYPE_MATERIALIZATION for g in resolution.gaps)