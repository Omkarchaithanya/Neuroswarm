"""Result aggregation — merge only, no inference / summarization."""

from __future__ import annotations

import time
from typing import Iterable, Mapping

from .events import AggregationFinished, EventBus
from .exceptions import AggregationError
from .metrics import OrchestratorMetrics
from .models import AggregatedResult, NodeResult


class ResultAggregator:
    """Pure coordination merge of node outputs / metadata / metrics / budgets."""

    def __init__(
        self,
        *,
        events: EventBus | None = None,
        metrics: OrchestratorMetrics | None = None,
    ) -> None:
        self.events = events
        self.metrics = metrics

    def aggregate(
        self,
        results: Iterable[NodeResult] | Mapping[str, NodeResult],
        *,
        workflow_id: str = "",
        execution_id: str = "",
        base: AggregatedResult | None = None,
    ) -> AggregatedResult:
        t0 = time.perf_counter()
        if isinstance(results, Mapping):
            items = list(results.values())
        else:
            items = list(results)

        out = AggregatedResult() if base is None else base.model_copy(deep=True)

        for result in items:
            if not isinstance(result, NodeResult):
                raise AggregationError(f"expected NodeResult, got {type(result)!r}")
            out.node_ids.append(result.node_id)
            out.outputs[result.node_id] = result.output
            # metadata: shallow merge, later wins on key collision at top level;
            # nest per-node under node_id to avoid clobber
            out.metadata[result.node_id] = dict(result.metadata)
            for k, v in result.metrics.items():
                out.metrics[k] = out.metrics.get(k, 0.0) + float(v)
            for k, v in result.budget_used.items():
                out.budgets[k] = out.budgets.get(k, 0.0) + float(v)
            for k, v in result.tool_outputs.items():
                key = f"{result.node_id}.{k}" if k in out.tool_outputs else k
                out.tool_outputs[key] = v
            for ref in result.memory_refs:
                if ref not in out.memory_refs:
                    out.memory_refs.append(ref)

        # de-dupe node_ids preserving order
        seen: set[str] = set()
        deduped: list[str] = []
        for nid in out.node_ids:
            if nid not in seen:
                seen.add(nid)
                deduped.append(nid)
        out.node_ids = deduped

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        if self.metrics is not None:
            self.metrics.observe_aggregation(elapsed_ms)
        if self.events is not None and workflow_id and execution_id:
            self.events.emit(
                AggregationFinished(
                    workflow_id,
                    execution_id,
                    node_count=len(out.node_ids),
                    aggregation_ms=elapsed_ms,
                )
            )
        return out

    def merge_pair(self, left: AggregatedResult, right: AggregatedResult) -> AggregatedResult:
        combined = [
            NodeResult(
                node_id=nid,
                output=left.outputs.get(nid),
                metadata=dict(left.metadata.get(nid, {}))
                if isinstance(left.metadata.get(nid), dict)
                else {},
            )
            for nid in left.node_ids
        ]
        combined.extend(
            NodeResult(
                node_id=nid,
                output=right.outputs.get(nid),
                metadata=dict(right.metadata.get(nid, {}))
                if isinstance(right.metadata.get(nid), dict)
                else {},
            )
            for nid in right.node_ids
            if nid not in left.node_ids
        )
        # Also fold metrics/budgets/tools from both
        base = AggregatedResult(
            metrics=dict(left.metrics),
            budgets=dict(left.budgets),
            tool_outputs=dict(left.tool_outputs),
            memory_refs=list(left.memory_refs),
        )
        for k, v in right.metrics.items():
            base.metrics[k] = base.metrics.get(k, 0.0) + float(v)
        for k, v in right.budgets.items():
            base.budgets[k] = base.budgets.get(k, 0.0) + float(v)
        for k, v in right.tool_outputs.items():
            base.tool_outputs[k] = v
        for ref in right.memory_refs:
            if ref not in base.memory_refs:
                base.memory_refs.append(ref)
        return self.aggregate(combined, base=base)
