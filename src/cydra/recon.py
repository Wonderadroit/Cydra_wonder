"""Passive structural reconnaissance and canonical system-model initialization for CYDRA."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import PurePosixPath
import ast
from typing import Callable, Iterable

from .scope import ScopeState


class NodeKind(str, Enum):
    FILE = "file"
    MODULE = "module"
    FUNCTION = "function"
    CLASS = "class"
    IMPORT = "import"
    ENTRY_POINT = "entry_point"
    AUTHORIZATION = "authorization"


@dataclass(frozen=True)
class ReconNode:
    node_id: str
    kind: NodeKind
    path: str
    name: str
    scope: ScopeState
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ReconEdge:
    source: str
    relation: str
    target: str


@dataclass
class SystemReconSnapshot:
    """Compatibility recon snapshot; canonical projection is explicit via ``to_canonical``."""
    nodes: list[ReconNode] = field(default_factory=list)
    edges: list[ReconEdge] = field(default_factory=list)

    def add_node(self, node: ReconNode) -> None:
        if not any(existing.node_id == node.node_id for existing in self.nodes):
            self.nodes.append(node)

    def add_edge(self, edge: ReconEdge) -> None:
        if edge not in self.edges:
            self.edges.append(edge)

    def active_nodes(self) -> list[ReconNode]:
        return [n for n in self.nodes if n.scope is ScopeState.IN_SCOPE]


class RepositoryRecon:
    """Build a minimal source structure from passive inspection."""

    def __init__(self, scope_resolver: Callable[[str], object]):
        self.scope_resolver = scope_resolver

    def _scope(self, path: str) -> ScopeState:
        return self.scope_resolver(path).state

    def scan(self, paths: Iterable[str], sources: dict[str, str]) -> SystemReconSnapshot:
        model = SystemReconSnapshot()
        for raw_path in paths:
            path = PurePosixPath(raw_path).as_posix()
            state = self._scope(path)
            model.add_node(ReconNode(f"file:{path}", NodeKind.FILE, path, PurePosixPath(path).name, state))
            if state is ScopeState.OUT_OF_SCOPE:
                continue
            source = sources.get(path)
            if source is not None and path.endswith(".py"):
                self._parse_python(path, source, model)
        return model

    def to_canonical(self, recon_model: SystemReconSnapshot, canonical=None):
        from .system_model import Edge, Node, SystemModel as CanonicalSystemModel
        canonical = canonical or CanonicalSystemModel()
        for recon_node in recon_model.nodes:
            canonical.add_node(Node(recon_node.node_id, recon_node.kind.value, recon_node.name, {
                "source": "repository_recon", "path": recon_node.path,
                "scope_state": recon_node.scope.value, "metadata": dict(recon_node.metadata),
            }))
        for recon_edge in recon_model.edges:
            canonical.add_edge(Edge(recon_edge.source, recon_edge.relation, recon_edge.target, {"provenance": "repository_recon"}))
        return canonical

    def scan_canonical(self, paths: Iterable[str], sources: dict[str, str], canonical=None):
        return self.to_canonical(self.scan(paths, sources), canonical)

    def _parse_python(self, path: str, source: str, model: SystemReconSnapshot) -> None:
        try:
            tree = ast.parse(source, filename=path)
        except SyntaxError:
            return
        state = self._scope(path)
        module_id = f"module:{path}"
        model.add_node(ReconNode(module_id, NodeKind.MODULE, path, PurePosixPath(path).stem, state))
        model.add_edge(ReconEdge(f"file:{path}", "contains", module_id))

        parent_map: dict[ast.AST, ast.AST] = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parent_map[child] = parent

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                function_id = f"function:{path}:{node.lineno}:{node.name}"
                metadata = {"line": str(node.lineno), "async": str(isinstance(node, ast.AsyncFunctionDef)).lower()}
                model.add_node(ReconNode(function_id, NodeKind.FUNCTION, path, node.name, state, metadata))
                parent = parent_map.get(node)
                if isinstance(parent, ast.ClassDef):
                    class_id = f"class:{path}:{parent.lineno}:{parent.name}"
                    model.add_edge(ReconEdge(class_id, "contains", function_id))
                else:
                    model.add_edge(ReconEdge(module_id, "contains", function_id))
                if node.name.startswith(("handle_", "route_", "api_")) or node.name in {"main", "run"}:
                    entry_id = f"entry:{path}:{node.lineno}:{node.name}"
                    model.add_node(ReconNode(entry_id, NodeKind.ENTRY_POINT, path, node.name, state))
                    model.add_edge(ReconEdge(function_id, "exposes", entry_id))
            elif isinstance(node, ast.ClassDef):
                class_id = f"class:{path}:{node.lineno}:{node.name}"
                model.add_node(ReconNode(class_id, NodeKind.CLASS, path, node.name, state, {"line": str(node.lineno)}))
                model.add_edge(ReconEdge(module_id, "contains", class_id))
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for imported in [alias.name for alias in node.names]:
                    import_id = f"import:{path}:{node.lineno}:{imported}"
                    model.add_node(ReconNode(import_id, NodeKind.IMPORT, path, imported, state, {"line": str(node.lineno)}))
                    model.add_edge(ReconEdge(module_id, "imports", import_id))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"login_required", "require_auth", "authorize", "authenticate"}:
                auth_id = f"authorization:{path}:{node.lineno}:{node.func.id}"
                model.add_node(ReconNode(auth_id, NodeKind.AUTHORIZATION, path, node.func.id, state, {"line": str(node.lineno)}))
                model.add_edge(ReconEdge(module_id, "uses_authorization", auth_id))
