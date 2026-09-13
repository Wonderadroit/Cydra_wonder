"""Loss-minimizing projection of the legacy InvestigationResult into SystemModel.

This adapter deliberately does not reinterpret or upgrade legacy conclusions. It
preserves their provenance and status while making the artifacts available to the
canonical reasoning graph for subsequent evidence-driven reasoning.
"""
from __future__ import annotations
from .models import InvestigationResult
from .system_model import Edge, Node, SystemModel


def project_investigation_result(result: InvestigationResult, model: SystemModel | None = None) -> SystemModel:
    model = model or SystemModel()
    for contract in result.contracts:
        contract_id = f"contract:{contract.source}:{contract.name}"
        model.add_node(Node(contract_id, "contract", contract.name, {"source": "legacy_investigation", "source_path": contract.source, "pragma": contract.pragma, "inherits": list(contract.inherits)}))
        for function in contract.functions:
            signature = ",".join(parameter.type for parameter in function.parameters)
            function_id = f"function:{contract.source}:{contract.name}:{function.name}({signature})"
            model.add_node(Node(function_id, "function", function.name or "<anonymous>", {"source": "legacy_investigation", "source_path": contract.source, "line": function.line, "visibility": function.visibility, "modifiers": list(function.modifiers), "authorization_predicates": list(function.authorization_predicates), "state_predicates": list(function.state_predicates)}))
            model.add_edge(Edge(function_id, "defined_in", contract_id, {"provenance": "legacy_investigation"}))
    for invariant in result.invariants:
        invariant_id = f"invariant:{invariant.invariant_id}"
        model.add_node(Node(invariant_id, "invariant", invariant.statement, {"provenance": invariant.provenance, "confidence": invariant.confidence, "legacy_status": "inferred"}))
    for hypothesis in result.hypotheses:
        hypothesis_id = f"hypothesis:{hypothesis.hypothesis_id}"
        model.add_node(Node(hypothesis_id, "hypothesis", hypothesis.claim, {"invariant_id": f"invariant:{hypothesis.invariant_id}", "target_function": hypothesis.target_function, "attacker_capability": hypothesis.attacker_capability, "expected_impact": hypothesis.expected_impact, "legacy_status": hypothesis.status, "evidence_ids": list(hypothesis.evidence_ids), "provenance": "legacy_investigation"}))
        invariant_id = f"invariant:{hypothesis.invariant_id}"
        if invariant_id in model.nodes:
            model.add_edge(Edge(invariant_id, "informs", hypothesis_id, {"provenance": "legacy_investigation"}))
    for evidence in result.evidence:
        evidence_id = f"evidence:{evidence.evidence_id}"
        model.add_node(Node(evidence_id, "evidence", evidence.claim, {"source": evidence.source, "location": evidence.location, "kind": evidence.kind, "provenance": "legacy_investigation"}))
    for experiment in result.experiments:
        observation_id = f"observation:{experiment.experiment_id}"
        model.add_node(Node(observation_id, "observation", experiment.action, {"hypothesis_id": f"hypothesis:{experiment.hypothesis_id}", "cost": experiment.cost, "discriminates": list(experiment.discriminates), "status": "planned", "provenance": "legacy_investigation"}))
        hypothesis_id = f"hypothesis:{experiment.hypothesis_id}"
        if hypothesis_id in model.nodes:
            model.add_edge(Edge(observation_id, "tests", hypothesis_id, {"provenance": "legacy_investigation"}))
    return model
