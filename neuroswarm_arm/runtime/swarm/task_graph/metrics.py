"""In-memory Task Graph metrics (no prometheus_client)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from .dag import DAGAnalyzer
from .enums import NodeStatus
from .graph import TaskGraph
from .models import GraphMetricsSnapshot, NodeMetricsSnapshot


@dataclass
class NodeMetrics:
    execution_time_s: float = 0.0
    queue_time_s: float = 0.0
    retries: int = 0
    failures: int = 0
    estimated_latency_ms: float = 0.0
    estimated_cost: float = 0.0
    memory_estimate_bytes: int = 0

    def snapshot(self) -> NodeMetricsSnapshot:
        return NodeMetricsSnapshot(
            execution_time_s=self.execution_time_s,
            queue_time_s=self.queue_time_s,
            retries=self.retries,
            failures=self.failures,
            estimated_latency_ms=self.estimated_latency_ms,
            estimated_cost=self.estimated_cost,
            memory_estimate_bytes=self.memory_estimate_bytes,
        )


@dataclass
class GraphMetrics:
    execution_time_s: float = 0.0
    queue_time_s: float = 0.0
    retries: int = 0
    failures: int = 0
    parallelism: float = 0.0
    depth: int = 0
    width: int = 0
    critical_path_length: int = 0
    critical_path_latency_ms: float = 0.0
    estimated_latency_ms: float = 0.0
    estimated_cost: float = 0.0
    memory_estimate_bytes: int = 0
    nodes_succeeded: int = 0
    nodes_failed: int = 0
    nodes_skipped: int = 0
    nodes_cancelled: int = 0
    node_metrics: dict[str, NodeMetrics] = field(default_factory=dict)

    def ensure_node(self, node_id: str) -> NodeMetrics:
        if node_id not in self.node_metrics:
            self.node_metrics[node_id] = NodeMetrics()
        return self.node_metrics[node_id]

    def snapshot(self) -> GraphMetricsSnapshot:
        return GraphMetricsSnapshot(
            execution_time_s=self.execution_time_s,
            queue_time_s=self.queue_time_s,
            retries=self.retries,
            failures=self.failures,
            parallelism=self.parallelism,
            depth=self.depth,
            width=self.width,
            critical_path_length=self.critical_path_length,
            critical_path_latency_ms=self.critical_path_latency_ms,
            estimated_latency_ms=self.estimated_latency_ms,
            estimated_cost=self.estimated_cost,
            memory_estimate_bytes=self.memory_estimate_bytes,
            nodes_succeeded=self.nodes_succeeded,
            nodes_failed=self.nodes_failed,
            nodes_skipped=self.nodes_skipped,
            nodes_cancelled=self.nodes_cancelled,
        )

    def record(self, name: str, value: float, *, labels: Mapping[str, str] | None = None) -> None:
        """IMetricsSink-compatible low-cardinality recorder."""
        # labels intentionally ignored for high-cardinality safety
        if name == "execution_time_s":
            self.execution_time_s += value
        elif name == "retries":
            self.retries += int(value)
        elif name == "failures":
            self.failures += int(value)


def compute_static_metrics(graph: TaskGraph) -> GraphMetrics:
    """Pre-execution structural estimates."""
    m = GraphMetrics()
    if not graph.nodes:
        return m
    analyzer = DAGAnalyzer(graph)
    if analyzer.is_dag():
        m.depth = analyzer.depth()
        m.width = analyzer.width()
        path = analyzer.critical_path()
        m.critical_path_length = len(path)
        m.critical_path_latency_ms = analyzer.critical_path_latency_ms()
        layers = analyzer.execution_layers()
        if layers:
            m.parallelism = sum(len(layer) for layer in layers) / len(layers)
    m.estimated_latency_ms = sum(n.estimated_latency for n in graph.nodes.values())
    m.estimated_cost = sum(n.estimated_cost for n in graph.nodes.values())
    m.memory_estimate_bytes = sum(n.memory_requirement for n in graph.nodes.values())
    for nid, node in graph.nodes.items():
        nm = m.ensure_node(nid)
        nm.estimated_latency_ms = node.estimated_latency
        nm.estimated_cost = node.estimated_cost
        nm.memory_estimate_bytes = node.memory_requirement
    return m


def tally_terminal_statuses(metrics: GraphMetrics, statuses: Mapping[str, NodeStatus]) -> None:
    metrics.nodes_succeeded = sum(1 for s in statuses.values() if s is NodeStatus.SUCCEEDED)
    metrics.nodes_failed = sum(1 for s in statuses.values() if s is NodeStatus.FAILED)
    metrics.nodes_skipped = sum(1 for s in statuses.values() if s is NodeStatus.SKIPPED)
    metrics.nodes_cancelled = sum(1 for s in statuses.values() if s is NodeStatus.CANCELLED)
