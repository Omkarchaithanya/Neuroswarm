"""Graph validation with human-readable reports."""

from __future__ import annotations

from typing import Any

from .conditions import condition_from_dict
from .dag import DAGAnalyzer
from .enums import Priority
from .exceptions import ConditionError, ValidationError
from .graph import TaskGraph
from .models import RetryPolicy, ValidationIssue, ValidationReport


class GraphValidator:
    """Validate structural + semantic integrity of a TaskGraph."""

    def validate(self, graph: TaskGraph, *, raise_on_error: bool = False) -> ValidationReport:
        issues: list[ValidationIssue] = []
        issues.extend(self._duplicate_ids(graph))
        issues.extend(self._cycles(graph))
        issues.extend(self._disconnected(graph))
        issues.extend(self._missing_deps(graph))
        issues.extend(self._node_fields(graph))
        issues.extend(self._edge_fields(graph))
        issues.extend(self._conditions(graph))
        report = ValidationReport(issues=tuple(issues), graph_id=graph.graph_id)
        if raise_on_error and not report.ok:
            raise ValidationError(report.format(), report=report)
        return report

    def _duplicate_ids(self, graph: TaskGraph) -> list[ValidationIssue]:
        # dict keys already unique; check edge key collisions soft-warn
        return []

    def _cycles(self, graph: TaskGraph) -> list[ValidationIssue]:
        analyzer = DAGAnalyzer(graph)
        if not analyzer.is_dag():
            return [
                ValidationIssue(
                    code="CYCLE",
                    message="graph contains a cycle",
                    severity="error",
                )
            ]
        return []

    def _disconnected(self, graph: TaskGraph) -> list[ValidationIssue]:
        if len(graph.nodes) <= 1:
            return []
        analyzer = DAGAnalyzer(graph)
        orphans = analyzer.disconnected_nodes()
        issues: list[ValidationIssue] = []
        for nid in orphans:
            issues.append(
                ValidationIssue(
                    code="DISCONNECTED_NODE",
                    message="node has no edges (orphaned)",
                    severity="warning",
                    node_id=nid,
                )
            )
        comps = analyzer.connected_components()
        if len(comps) > 1:
            issues.append(
                ValidationIssue(
                    code="MULTIPLE_COMPONENTS",
                    message=f"graph has {len(comps)} weakly connected components",
                    severity="warning",
                    details={"components": [sorted(c) for c in comps]},
                )
            )
        return issues

    def _missing_deps(self, graph: TaskGraph) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        analyzer = DAGAnalyzer(graph)
        for src, dst in analyzer.missing_dependencies():
            issues.append(
                ValidationIssue(
                    code="MISSING_DEPENDENCY",
                    message="edge or dependency references unknown node",
                    severity="error",
                    edge=(src, dst),
                )
            )
        for nid, node in graph.nodes.items():
            for child in node.children:
                if child not in graph.nodes:
                    issues.append(
                        ValidationIssue(
                            code="MISSING_CHILD",
                            message=f"child {child} not in graph",
                            severity="error",
                            node_id=nid,
                        )
                    )
        return issues

    def _node_fields(self, graph: TaskGraph) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for nid, node in graph.nodes.items():
            for msg in node.validate_node():
                issues.append(
                    ValidationIssue(
                        code="INVALID_NODE",
                        message=msg,
                        severity="error",
                        node_id=nid,
                    )
                )
            if node.priority not in list(Priority):
                issues.append(
                    ValidationIssue(
                        code="INVALID_PRIORITY",
                        message=f"priority {node.priority} out of range",
                        severity="error",
                        node_id=nid,
                    )
                )
            try:
                RetryPolicy.model_validate(node.retry_policy.model_dump())
            except Exception as exc:  # noqa: BLE001
                issues.append(
                    ValidationIssue(
                        code="INVALID_RETRY_POLICY",
                        message=str(exc),
                        severity="error",
                        node_id=nid,
                    )
                )
            if node.timeout is not None and node.timeout <= 0:
                issues.append(
                    ValidationIssue(
                        code="INVALID_TIMEOUT",
                        message="timeout must be > 0",
                        severity="error",
                        node_id=nid,
                    )
                )
            if node.metadata is not None and not isinstance(node.metadata, dict):
                issues.append(
                    ValidationIssue(
                        code="INVALID_METADATA",
                        message="metadata must be a dict",
                        severity="error",
                        node_id=nid,
                    )
                )
        try:
            if graph.timeout_policy.workflow_timeout_s is not None:
                _ = graph.timeout_policy.workflow_timeout_s
        except Exception as exc:  # noqa: BLE001
            issues.append(
                ValidationIssue(
                    code="INVALID_TIMEOUT",
                    message=f"graph timeout_policy invalid: {exc}",
                    severity="error",
                )
            )
        return issues

    def _edge_fields(self, graph: TaskGraph) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for edge in graph.edges:
            if edge.src == edge.dst:
                issues.append(
                    ValidationIssue(
                        code="SELF_LOOP",
                        message="edge src == dst",
                        severity="error",
                        edge=(edge.src, edge.dst),
                    )
                )
        return issues

    def _conditions(self, graph: TaskGraph) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for nid, node in graph.nodes.items():
            if node.condition is None:
                continue
            try:
                condition_from_dict(node.condition)
            except (ConditionError, KeyError, TypeError, ValueError) as exc:
                issues.append(
                    ValidationIssue(
                        code="INVALID_CONDITION",
                        message=str(exc),
                        severity="error",
                        node_id=nid,
                    )
                )
        for edge in graph.edges:
            if edge.condition is None:
                continue
            try:
                condition_from_dict(edge.condition)
            except (ConditionError, KeyError, TypeError, ValueError) as exc:
                issues.append(
                    ValidationIssue(
                        code="INVALID_CONDITION",
                        message=str(exc),
                        severity="error",
                        edge=(edge.src, edge.dst),
                    )
                )
        return issues


def validate_graph(graph: TaskGraph, *, raise_on_error: bool = False) -> ValidationReport:
    return GraphValidator().validate(graph, raise_on_error=raise_on_error)
