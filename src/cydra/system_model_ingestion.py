"""Canonical projection boundary for source observations into SystemModel."""
from __future__ import annotations

from .recon import NodeKind, RepositoryRecon
from .repository_model import RepositoryModel
from .system_model import Edge, Node, SystemModel

_KIND_MAP = {
    NodeKind.FILE: "contract",
    NodeKind.MODULE: "contract",
    NodeKind.FUNCTION: "function",
    NodeKind.CLASS: "contract",
    NodeKind.IMPORT: "data_flow",
    NodeKind.ENTRY_POINT: "function",
    NodeKind.AUTHORIZATION: "identity",
}


def project_recon_model(recon_model, system: SystemModel) -> None:
    for node in recon_model.nodes:
        attributes = dict(node.metadata)
        attributes.update(path=node.path, scope=node.scope.value, recon_kind=node.kind.value)
        if node.node_id not in system.nodes:
            system.add_node(Node(node.node_id, _KIND_MAP[node.kind], node.name, attributes))
    for edge in recon_model.edges:
        if edge.source in system.nodes and edge.target in system.nodes:
            system.add_edge(Edge(edge.source, edge.relation, edge.target, {"provenance": "passive_recon"}))


def project_repository_model(repository: RepositoryModel, system: SystemModel) -> None:
    for contract in sorted(repository.contracts, key=lambda c: (c.file, c.name)):
        cid = f"contract:{contract.file}:{contract.name}"
        if cid not in system.nodes:
            system.add_node(Node(cid, "contract", contract.name, {
                "file": contract.file,
                "state_variables": list(contract.state_variables),
                "source_kind": "repository_model",
            }))
        for state in sorted(contract.state_variables):
            sid = f"state:{contract.file}:{contract.name}:{state}"
            if sid not in system.nodes:
                system.add_node(Node(sid, "state_variable", state, {
                    "file": contract.file, "contract": cid, "source_kind": "repository_model",
                }))
            system.add_edge(Edge(sid, "defined_in", cid))
        for fn in sorted(contract.functions, key=lambda f: (f.line or 0, f.name)):
            fid = f"function:{fn.file}:{fn.line}:{contract.name}:{fn.name}"
            if fid not in system.nodes:
                system.add_node(Node(fid, "function", fn.name, {
                    "file": fn.file, "line": fn.line, "visibility": fn.visibility,
                    "modifiers": list(fn.modifiers), "external_calls": list(fn.external_calls),
                    "source_kind": "repository_model",
                }))
            system.add_edge(Edge(fid, "defined_in", cid))


def scan_repository_into_system_model(paths, sources, scope_resolver):
    recon_model = RepositoryRecon(scope_resolver).scan(paths, sources)
    system = SystemModel()
    project_recon_model(recon_model, system)
    return system
