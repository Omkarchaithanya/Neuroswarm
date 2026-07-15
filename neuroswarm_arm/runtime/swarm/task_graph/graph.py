"""TaskGraph — mutable builder surface that freezes into an immutable definition."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, Mapping

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from .dag import DAGAnalyzer
from .edge import TaskEdge
from .enums import EdgeKind, NodeStatus
from .exceptions import FrozenGraphError, NodeNotFoundError
from .models import GraphMeta, TimeoutPolicy
from .node import TaskNode
from .utils import new_id, stable_hash, utc_now


class TaskGraph(BaseModel):
    """Canonical workflow DAG.

    Before ``freeze()``: mutable (add/remove/replace nodes & edges).
    After ``freeze()``: definition locked; use ``clone()`` / ``unfreeze()`` for edits.
    Execution mutates ``ExecutionState``, not this object.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True, arbitrary_types_allowed=True)

    graph_id: str = Field(default_factory=lambda: new_id("g_"))
    name: str = ""
    description: str = ""
    version: str = "1.0.0"
    schema_version: int = 1
    nodes: dict[str, TaskNode] = Field(default_factory=dict)
    edges: list[TaskEdge] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    timeout_policy: TimeoutPolicy = Field(default_factory=TimeoutPolicy)
    parent_graph_id: str | None = None
    subgraphs: dict[str, "TaskGraph"] = Field(default_factory=dict)
    created_at: Any = Field(default_factory=utc_now)
    updated_at: Any = Field(default_factory=utc_now)

    _frozen: bool = PrivateAttr(default=False)

    # --- mutability guards -------------------------------------------------

    def _ensure_mutable(self) -> None:
        if self._frozen:
            raise FrozenGraphError("graph is frozen; clone() or unfreeze() before mutating")

    @property
    def frozen(self) -> bool:
        return self._frozen

    def freeze(self) -> TaskGraph:
        self._sync_dep_links()
        self._frozen = True
        self.updated_at = utc_now()
        return self

    def unfreeze(self) -> TaskGraph:
        self._frozen = False
        return self

    def _sync_dep_links(self) -> None:
        """Refresh node.dependencies / children from edges."""
        deps: dict[str, list[str]] = {nid: [] for nid in self.nodes}
        children: dict[str, list[str]] = {nid: [] for nid in self.nodes}
        for edge in self.edges:
            if edge.src in children:
                children[edge.src].append(edge.dst)
            if edge.dst in deps:
                deps[edge.dst].append(edge.src)
        for nid, node in self.nodes.items():
            self.nodes[nid] = node.model_copy(
                update={
                    "dependencies": list(dict.fromkeys(deps.get(nid, []))),
                    "children": list(dict.fromkeys(children.get(nid, []))),
                    "updated_at": utc_now(),
                }
            )

    # --- node ops ----------------------------------------------------------

    def add_node(self, node: TaskNode | Mapping[str, Any], **kwargs: Any) -> TaskNode:
        self._ensure_mutable()
        if isinstance(node, Mapping):
            node = TaskNode.model_validate({**dict(node), **kwargs})
        elif kwargs:
            node = node.model_copy(update=kwargs)
        if node.id in self.nodes:
            raise ValueError(f"duplicate node id: {node.id}")
        self.nodes[node.id] = node
        self.updated_at = utc_now()
        return node

    def remove_node(self, node_id: str) -> TaskNode:
        self._ensure_mutable()
        if node_id not in self.nodes:
            raise NodeNotFoundError(node_id)
        removed = self.nodes.pop(node_id)
        self.edges = [e for e in self.edges if e.src != node_id and e.dst != node_id]
        for sg_id, sg in list(self.subgraphs.items()):
            if sg.graph_id == node_id:
                del self.subgraphs[sg_id]
        self.updated_at = utc_now()
        return removed

    def replace_node(self, node_id: str, new_node: TaskNode) -> TaskNode:
        self._ensure_mutable()
        if node_id not in self.nodes:
            raise NodeNotFoundError(node_id)
        if new_node.id != node_id and new_node.id in self.nodes:
            raise ValueError(f"replacement id collides: {new_node.id}")
        old_id = node_id
        del self.nodes[old_id]
        if new_node.id != old_id:
            for i, edge in enumerate(self.edges):
                upd: dict[str, Any] = {}
                if edge.src == old_id:
                    upd["src"] = new_node.id
                if edge.dst == old_id:
                    upd["dst"] = new_node.id
                if upd:
                    self.edges[i] = edge.model_copy(update=upd)
        self.nodes[new_node.id] = new_node
        self.updated_at = utc_now()
        return new_node

    def get_node(self, node_id: str) -> TaskNode:
        try:
            return self.nodes[node_id]
        except KeyError as exc:
            raise NodeNotFoundError(node_id) from exc

    # --- edge ops ----------------------------------------------------------

    def add_edge(
        self,
        src: str | TaskNode,
        dst: str | TaskNode,
        *,
        kind: EdgeKind = EdgeKind.HARD,
        label: str = "",
        condition: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        priority_boost: int = 0,
        data_key: str | None = None,
    ) -> TaskEdge:
        self._ensure_mutable()
        src_id = src.id if isinstance(src, TaskNode) else src
        dst_id = dst.id if isinstance(dst, TaskNode) else dst
        if src_id not in self.nodes or dst_id not in self.nodes:
            missing = src_id if src_id not in self.nodes else dst_id
            raise NodeNotFoundError(missing)
        edge = TaskEdge(
            src=src_id,
            dst=dst_id,
            kind=kind,
            label=label,
            condition=condition,
            metadata=metadata or {},
            priority_boost=priority_boost,
            data_key=data_key,
        )
        self.edges.append(edge)
        self.updated_at = utc_now()
        return edge

    def remove_edge(self, src: str, dst: str, *, kind: EdgeKind | None = None) -> int:
        self._ensure_mutable()
        before = len(self.edges)
        self.edges = [
            e
            for e in self.edges
            if not (e.src == src and e.dst == dst and (kind is None or e.kind is kind))
        ]
        removed = before - len(self.edges)
        if removed:
            self.updated_at = utc_now()
        return removed

    # --- graph ops ---------------------------------------------------------

    def merge(self, other: TaskGraph, *, prefix: str = "") -> TaskGraph:
        self._ensure_mutable()
        from .utils import new_id as gen_id

        id_map: dict[str, str] = {}
        for nid, node in other.nodes.items():
            candidate = f"{prefix}{nid}" if prefix else nid
            mapped = gen_id("n_") if candidate in self.nodes else candidate
            id_map[nid] = mapped
            self.nodes[mapped] = node.clone(new_id_value=mapped)
        for edge in other.edges:
            self.edges.append(
                edge.model_copy(
                    update={"src": id_map[edge.src], "dst": id_map[edge.dst]}
                )
            )
        for sg_id, sg in other.subgraphs.items():
            self.subgraphs[f"{prefix}{sg_id}"] = sg.clone()
        self.metadata = {**self.metadata, **deepcopy(other.metadata)}
        self.updated_at = utc_now()
        return self

    def split(self, node_ids: Iterable[str]) -> tuple[TaskGraph, TaskGraph]:
        """Split into subgraph containing ``node_ids`` and remainder."""
        keep = set(node_ids)
        left = TaskGraph(
            name=f"{self.name}:part",
            parent_graph_id=self.graph_id,
            metadata=deepcopy(self.metadata),
        )
        right = TaskGraph(
            name=f"{self.name}:rest",
            parent_graph_id=self.graph_id,
            metadata=deepcopy(self.metadata),
        )
        for nid, node in self.nodes.items():
            target = left if nid in keep else right
            target.nodes[nid] = node.clone(new_id_value=nid)
        for edge in self.edges:
            if edge.src in keep and edge.dst in keep:
                left.edges.append(edge.clone())
            elif edge.src not in keep and edge.dst not in keep:
                right.edges.append(edge.clone())
        return left, right

    def clone(self, *, new_graph_id: bool = True) -> TaskGraph:
        data = self.model_dump(mode="python")
        if new_graph_id:
            data["graph_id"] = new_id("g_")
        data["created_at"] = utc_now()
        data["updated_at"] = utc_now()
        cloned = TaskGraph.model_validate(data)
        cloned._frozen = False
        return cloned

    def extract_subgraph(self, node_ids: Iterable[str]) -> TaskGraph:
        keep = set(node_ids)
        sg = TaskGraph(
            name=f"{self.name}:subgraph",
            parent_graph_id=self.graph_id,
            metadata=deepcopy(self.metadata),
        )
        for nid in keep:
            if nid not in self.nodes:
                raise NodeNotFoundError(nid)
            sg.nodes[nid] = self.nodes[nid].clone(new_id_value=nid)
        for edge in self.edges:
            if edge.src in keep and edge.dst in keep:
                sg.edges.append(edge.clone())
        return sg

    def attach_subgraph(self, key: str, subgraph: TaskGraph) -> None:
        self._ensure_mutable()
        self.subgraphs[key] = subgraph.clone()
        self.updated_at = utc_now()

    # --- analysis proxies --------------------------------------------------

    def analyzer(self) -> DAGAnalyzer:
        return DAGAnalyzer(self)

    def topological_sort(self) -> list[str]:
        return self.analyzer().topological_order()

    def has_cycle(self) -> bool:
        return not self.analyzer().is_dag()

    def execution_layers(self) -> list[list[str]]:
        return self.analyzer().execution_layers()

    def critical_path(self) -> list[str]:
        return self.analyzer().critical_path()

    def roots(self) -> list[str]:
        return self.analyzer().roots()

    def leaves(self) -> list[str]:
        return self.analyzer().leaves()

    # --- hashing / versioning ----------------------------------------------

    def definition_payload(self) -> dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "schema_version": self.schema_version,
            "nodes": {
                nid: n.definition_payload()
                for nid, n in sorted(self.nodes.items(), key=lambda x: x[0])
            },
            "edges": [e.definition_payload() for e in self.edges],
            "metadata": self.metadata,
            "tags": list(self.tags),
            "timeout_policy": self.timeout_policy.model_dump(mode="json"),
            "parent_graph_id": self.parent_graph_id,
            "subgraphs": {
                k: v.definition_payload() for k, v in sorted(self.subgraphs.items())
            },
        }

    def content_hash(self) -> str:
        return stable_hash(self.definition_payload())

    def meta(self) -> GraphMeta:
        return GraphMeta(
            version=self.version,
            schema_version=self.schema_version,
            name=self.name,
            description=self.description,
            tags=tuple(self.tags),
            metadata=dict(self.metadata),
            parent_graph_id=self.parent_graph_id,
        )

    def propagate_metadata(self, overlay: Mapping[str, Any]) -> None:
        """Push metadata overlay onto graph + all nodes (mutable only)."""
        self._ensure_mutable()
        self.metadata = {**self.metadata, **dict(overlay)}
        for nid, node in self.nodes.items():
            self.nodes[nid] = node.model_copy(
                update={"metadata": {**node.metadata, **dict(overlay)}, "updated_at": utc_now()}
            )
        self.updated_at = utc_now()

    def reset_runtime(self) -> None:
        """Clear runtime fields on all nodes (definition stays)."""
        self._ensure_mutable()
        for nid, node in self.nodes.items():
            self.nodes[nid] = node.model_copy(
                update={
                    "status": NodeStatus.PENDING,
                    "result": None,
                    "error": None,
                    "events": [],
                    "execution_state": {},
                    "metrics": {},
                    "updated_at": utc_now(),
                }
            )

    def bump_version(self, new_version: str) -> None:
        self._ensure_mutable()
        self.version = new_version
        self.updated_at = utc_now()
