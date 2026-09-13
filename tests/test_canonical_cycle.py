from cydra.canonical_cycle import run_canonical_differential_cycle
from cydra.finding_gate import FindingCandidate, GateDecision, evaluate_finding_graph
from cydra.foundry import ExecutionResult
from cydra.hypotheses import Hypothesis, HypothesisState
from cydra.system_model import Edge, Node, SystemModel


def execution(experiment_id, target, status):
    return ExecutionResult(
        experiment_id,
        target,
        ("forge", "test"),
        1 if status == "FAIL" else 0,
        True,
        1,
        1 if status == "FAIL" else 0,
        status,
        "",
        "",
    )


def build_model():
    graph = SystemModel()
    graph.add_node(Node("hypothesis:h1", "hypothesis", "unauthorized mutation", {"state": "unresolved", "belief": 0.5}))
    graph.add_node(Node("observation:o1", "observation", "unauthorized mutation probe", {
        "status": "planned",
        "target_function_id": "function:f1",
        "binding_status": "bound",
        "experiment_binding": {
            "hypothesis_id": "hypothesis:h1",
            "observation_id": "observation:o1",
            "target_function_id": "function:f1",
            "source_marker": "CYDRA-HYPOTHESIS: h1",
        },
    }))
    graph.add_node(Node("function:f1", "function", "setWhitelist"))
    graph.add_node(Node("invariant:i1", "invariant", "authorization boundary"))
    graph.add_edge(Edge("observation:o1", "tests", "hypothesis:h1"))
    graph.add_edge(Edge("observation:o1", "targets", "invariant:i1"))
    return graph


def test_executed_differential_establishes_hypothesis_and_unlocks_finding_gate():
    graph = build_model()
    result = run_canonical_differential_cycle(
        graph,
        hypothesis=Hypothesis("h1", "unauthorized caller can mutate privileged state"),
        observation_id="o1",
        vulnerable=execution("vulnerable", "vulnerable", "FAIL"),
        patched=execution("patched", "patched", "PASS"),
        outcome_id="cycle-1",
    )
    assert result.hypothesis.state is HypothesisState.CAUSALLY_ESTABLISHED
    assert result.belief_update.posterior_state is HypothesisState.CAUSALLY_ESTABLISHED
    assert result.causal_verification.state.value == "verified"
    assert graph.nodes["hypothesis:h1"].attributes["state"] == "causally_established"
    assert graph.nodes["belief:cycle-1"].attributes["posterior_state"] == "causally_established"
    gate = evaluate_finding_graph(
        graph,
        candidate=FindingCandidate(True, False, True, True, True, True),
        finding_id="finding:1",
        hypothesis_id="hypothesis:h1",
        evidence_ids=result.causal_verification.evidence_ids,
        causal_chain_id=result.causal_chain.chain_id,
    )
    assert gate.decision is GateDecision.READY


def test_non_differential_execution_does_not_establish_hypothesis():
    graph = build_model()
    result = run_canonical_differential_cycle(
        graph,
        hypothesis=Hypothesis("h1", "unauthorized caller can mutate privileged state"),
        observation_id="o1",
        vulnerable=execution("vulnerable", "vulnerable", "PASS"),
        patched=execution("patched", "patched", "PASS"),
        outcome_id="cycle-2",
    )
    assert result.hypothesis.state is HypothesisState.UNRESOLVED
    assert result.verification.state.value == "unresolved"
    assert graph.nodes["hypothesis:h1"].attributes["state"] == "unresolved"
    assert graph.nodes["belief:cycle-2"].attributes["posterior_state"] == "unresolved"


def test_reversed_differential_contradicts_hypothesis_without_unlocking_finding_gate():
    graph = build_model()
    result = run_canonical_differential_cycle(
        graph,
        hypothesis=Hypothesis("h1", "unauthorized caller can mutate privileged state"),
        observation_id="o1",
        vulnerable=execution("vulnerable", "vulnerable", "PASS"),
        patched=execution("patched", "patched", "FAIL"),
        outcome_id="cycle-3",
    )
    assert result.hypothesis.state is HypothesisState.CONTRADICTED
    assert result.belief_update.posterior_state is HypothesisState.CONTRADICTED
    assert result.causal_verification.state.value == "verified"
    assert graph.nodes["hypothesis:h1"].attributes["state"] == "contradicted"
    gate = evaluate_finding_graph(
        graph,
        candidate=FindingCandidate(True, False, True, True, True, True),
        finding_id="finding:1",
        hypothesis_id="hypothesis:h1",
        evidence_ids=result.causal_verification.evidence_ids,
        causal_chain_id=result.causal_chain.chain_id,
    )
    assert gate.decision is GateDecision.BLOCKED
