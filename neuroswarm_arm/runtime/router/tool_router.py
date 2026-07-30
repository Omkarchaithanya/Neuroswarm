"""Semantic MCP Tool Router orchestrator."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .agent_filter import AgentFilter
from .arm import detect_arm_features, pin_current_thread
from .confidence import below_threshold, estimate_confidence
from .context_filter import ContextFilter
from .embedding_service import EmbeddingService
from .history_ranker import HistoryRanker
from .hybrid_search import HybridSearch
from .incremental_index import IncrementalIndexer
from .index_snapshot import IndexSnapshotManager
from .models import RouteContext, RoutingResult, ScoredTool, ToolRecord
from .registry import ToolRegistry
from .registry_loader import RegistryLoader
from .reranker import Reranker
from .router_config import RouterConfig
from .router_events import RouterEventBus, RouterEventKind
from .router_exceptions import ToolNotFoundError
from .router_metrics import RouterMetrics
from .similarity import keyword_overlap
from .telemetry import RouterTelemetry
from .tool_filter import ToolFilter
from .tool_registry_sync import ToolRegistrySync
from .tool_schema_builder import build_tool_schema
from .tool_serializer import schemas_from_result, serialize_tools_for_prompt, token_stats_for_registry
from .workflow_filter import WorkflowFilter


class SemanticToolRouter:
    """Production Semantic MCP Tool Router."""

    def __init__(
        self,
        *,
        config: RouterConfig,
        registry: ToolRegistry,
        embedder: EmbeddingService,
        index: Any,
        metrics: RouterMetrics,
        events: RouterEventBus,
        history: HistoryRanker,
        hybrid: HybridSearch,
        reranker: Reranker,
        indexer: IncrementalIndexer,
        snapshots: IndexSnapshotManager,
        sync: ToolRegistrySync | None = None,
        telemetry: RouterTelemetry | None = None,
    ) -> None:
        self.config = config
        self.registry = registry
        self.embedder = embedder
        self.index = index
        self.metrics = metrics
        self.events = events
        self.history = history
        self.hybrid = hybrid
        self.reranker = reranker
        self.indexer = indexer
        self.snapshots = snapshots
        self.sync = sync
        self.telemetry = telemetry or RouterTelemetry()
        self.arm_features = detect_arm_features()
        self.tool_filter = ToolFilter()
        self.workflow_filter = WorkflowFilter()
        self.context_filter = ContextFilter()
        self.agent_filter = AgentFilter()
        self.loader = RegistryLoader()
        if config.affinity_cores:
            pin_current_thread(config.affinity_cores)

    # ---- registry API ----
    def register_tool(self, tool: ToolRecord | dict[str, Any]) -> ToolRecord:
        record = tool if isinstance(tool, ToolRecord) else ToolRecord.from_dict(tool)
        self.registry.register(record)
        self.indexer.upsert(record)
        self.metrics.inc("router_register_total")
        self.metrics.set("router_tools_registered", float(self.registry.size()))
        self.metrics.set("router_index_size", float(self.index.size()))
        return record

    def remove_tool(self, tool_id: str) -> ToolRecord:
        tool = self.registry.remove(tool_id)
        self.indexer.remove(tool_id)
        self.metrics.set("router_tools_registered", float(self.registry.size()))
        self.metrics.set("router_index_size", float(self.index.size()))
        return tool

    def update_tool(self, tool_id: str, **fields: Any) -> ToolRecord:
        record = self.registry.update(tool_id, **fields)
        self.indexer.upsert(record)
        return record

    def get_tool(self, tool_id: str) -> ToolRecord:
        return self.registry.get(tool_id)

    def list_tools(self) -> list[ToolRecord]:
        return self.registry.as_list()

    def index_tools(self) -> int:
        count = self.indexer.rebuild(self.registry.as_list())
        self.metrics.set("router_index_size", float(count))
        return count

    # ---- search / route ----
    def search(
        self,
        query: str,
        *,
        k: int | None = None,
        context: RouteContext | None = None,
    ) -> list[ScoredTool]:
        return self.route(query, context=context, top_k=k).tools

    def route(
        self,
        query: str,
        *,
        context: RouteContext | None = None,
        top_k: int | None = None,
    ) -> RoutingResult:
        timer = self.metrics.timer()
        ctx = context or RouteContext()
        k = int(top_k or self.config.top_k)
        tools = self.registry.as_list()
        if not tools:
            return RoutingResult(query=query, top_k=k)

        with self.telemetry.span(
            "router.route",
            {
                "query_len": len(query),
                "top_k": k,
                "gen_ai.system": "neuroswarm",
                "gen_ai.provider.name": "neuroswarm",
                "gen_ai.operation.name": "route",
            },
        ):
            tools = self.tool_filter.apply(tools, ctx)
            tools = self.workflow_filter.apply(tools, ctx)
            tools = self.agent_filter.apply(tools, ctx)
            tools = self.context_filter.apply(tools, ctx)

            emb_timer = self.metrics.timer()
            with self.telemetry.span(
                "router.embed",
                {
                    "gen_ai.system": "neuroswarm",
                    "gen_ai.provider.name": "neuroswarm",
                    "gen_ai.operation.name": "embed",
                },
            ):
                qvec = self.embedder.encode_query(query)
            self.metrics.set("router_embedding_latency_ms", emb_timer.ms())

            candidate_k = min(len(tools), max(k * self.config.candidate_multiplier, k))
            ann_timer = self.metrics.timer()
            with self.telemetry.span("router.ann"):
                hits = self.index.search(qvec, candidate_k)
            ann_ms = ann_timer.ms()
            self.metrics.set("router_ann_latency_ms", ann_ms)
            self.metrics.set("router_search_latency_ms", ann_ms)
            # Only claim TurboVec latency when TurboVec actually handled the search.
            kernel = str(getattr(self.index, "kernel_path", "") or "")
            if kernel == "turbovec" or bool(getattr(self.index, "_using_turbovec", False)):
                self.metrics.set("router_turbovec_search_ms", ann_ms)

            id_to_tool = {t.id: t for t in tools}
            semantic_hits: list[tuple[ToolRecord, float]] = []
            for hit in hits:
                tool = id_to_tool.get(hit.key)
                if tool is not None:
                    semantic_hits.append((tool, float(hit.score)))

            # Ensure coverage if ANN miss / cold index
            if len(semantic_hits) < k:
                for tool in tools:
                    if tool.id in {t.id for t, _ in semantic_hits}:
                        continue
                    score = keyword_overlap(query, tool.index_text())
                    semantic_hits.append((tool, score))
                    if len(semantic_hits) >= candidate_k:
                        break

            top_sem = semantic_hits[0][1] if semantic_hits else 0.0
            if below_threshold(top_sem, self.config.threshold):
                # Expand with param-signature secondary ranking — always capped at candidate_k.
                expanded: list[tuple[ToolRecord, float]] = []
                for tool in tools:
                    param_score = keyword_overlap(
                        query, " ".join(tool.params.keys()) + " " + " ".join(tool.params.values())
                    )
                    base = next((s for t, s in semantic_hits if t.id == tool.id), 0.0)
                    expanded.append((tool, max(base, param_score)))
                expanded.sort(key=lambda x: x[1], reverse=True)
                semantic_hits = expanded[:candidate_k]

            history_scores = self.history.scores_for(ctx.agent_id, [t for t, _ in semantic_hits], query)
            fused = self.hybrid.fuse(query, semantic_hits, context=ctx, history_scores=history_scores)

            okf_scores = {
                c.tool.id: keyword_overlap(query, c.tool.description + " " + " ".join(c.tool.example_prompts))
                for c in fused
            }

            rerank_timer = self.metrics.timer()
            with self.telemetry.span("router.rerank"):
                ranked = self.reranker.rerank(
                    fused,
                    ctx,
                    history_scores=history_scores,
                    okf_scores=okf_scores,
                    top_k=k,
                )
            self.metrics.set("router_rerank_latency_ms", rerank_timer.ms())

            confidence = estimate_confidence(ranked)
            high_confidence = bool(confidence > float(self.config.high_conf_gate))
            before, after = token_stats_for_registry(self.registry.as_list(), ranked)
            latency = timer.ms()
            result = RoutingResult(
                tools=ranked,
                top_k=k,
                confidence_top1=confidence,
                high_confidence=high_confidence,
                prompt_tokens_before=before,
                prompt_tokens_after=after,
                latency_breakdown_ms={
                    "total": latency,
                    "embed": emb_timer.ms(),
                    "ann": ann_ms,
                    "rerank": rerank_timer.ms(),
                },
                features_debug={
                    "threshold": self.config.threshold,
                    "high_conf_gate": self.config.high_conf_gate,
                    "candidate_k": candidate_k,
                    "ann_backend": getattr(self.index, "backend_name", "unknown"),
                },
                query=query,
                candidate_count=len(semantic_hits),
            )
            self.metrics.observe_route(
                confidence=confidence,
                tools_returned=len(ranked),
                prompt_reduction=result.token_reduction_ratio(),
                token_reduction=result.token_reduction_ratio(),
                latency_ms=latency,
            )
            self.events.emit(
                RouterEventKind.ROUTED,
                query=query,
                tool_ids=result.tool_ids,
                confidence=confidence,
            )
            return result

    def batch_route(
        self,
        queries: list[str],
        *,
        context: RouteContext | None = None,
        top_k: int | None = None,
    ) -> list[RoutingResult]:
        return [self.route(q, context=context, top_k=top_k) for q in queries]

    def route_result(
        self,
        query: str,
        *,
        context: RouteContext | None = None,
        top_k: int | None = None,
    ) -> RoutingResult:
        """Alias used by gateway / HAOE chat adapters."""
        return self.route(query, context=context, top_k=top_k)

    # Compat with HAOE SupportsRoute
    def route_tools(self, query: str) -> list[ToolRecord]:
        return [s.tool for s in self.route(query).tools]

    # ---- lifecycle ----
    def reload(self) -> dict[str, object]:
        loaded = 0
        for root in [self.config.tool_metadata_root, self.config.okf_root]:
            if root.exists():
                tools = self.loader.load_path(root)
                self.registry.bulk_register(tools)
                loaded += len(tools)
        count = self.index_tools()
        sync_stats = self.sync.scan() if self.sync else {}
        self.events.emit(RouterEventKind.RELOAD, loaded=loaded, indexed=count, sync=sync_stats)
        return {"loaded": loaded, "indexed": count, "sync": sync_stats}

    def snapshot(self, name: str | None = None) -> str:
        path = self.snapshots.snapshot(name)
        return str(path)

    def restore(self, name_or_path: str) -> dict[str, object]:
        return self.snapshots.restore(name_or_path)

    def health(self) -> dict[str, object]:
        from .health import build_health_report

        return build_health_report(self)

    def metrics_snapshot(self) -> dict[str, float]:
        return self.metrics.snapshot()

    def prompt_block(self, result: RoutingResult) -> str:
        tools = self._executable_scored(result.tools)
        return serialize_tools_for_prompt(tools)

    def schemas(self, result: RoutingResult) -> list[dict[str, Any]]:
        tools = self._executable_scored(result.tools)
        if tools is result.tools:
            return schemas_from_result(result)
        filtered = RoutingResult(
            tools=tools,
            top_k=result.top_k,
            confidence_top1=result.confidence_top1,
            high_confidence=result.high_confidence,
            prompt_tokens_before=result.prompt_tokens_before,
            prompt_tokens_after=result.prompt_tokens_after,
            latency_breakdown_ms=dict(result.latency_breakdown_ms),
            features_debug=dict(result.features_debug),
            query=result.query,
            candidate_count=result.candidate_count,
        )
        return schemas_from_result(filtered)

    def _executable_scored(self, scored: list) -> list:
        """When MCP execute is on, inject only tools/list-reconciled executable tools."""
        from .mcp_executor import mcp_execute_enabled

        if not mcp_execute_enabled():
            return scored
        return [s for s in scored if getattr(s.tool, "executable", False)]

    def apply_mcp_reconcile(self, executable_ids: set[str]) -> int:
        """Mark ToolRecords executable after live tools/list reconcile."""
        n = 0
        for tool in self.registry.as_list():
            flag = tool.id in executable_ids
            self.registry.update(tool.id, executable=flag)
            if flag:
                n += 1
        return n

    async def reconcile_mcp_execute(self, *, timeout_s: float = 30.0) -> dict[str, object]:
        """Discover live MCP tools/list and mark registry tools executable."""
        from .mcp_executor import get_mcp_manager, mcp_execute_enabled

        if not mcp_execute_enabled():
            return {"skipped": True, "reason": "NSA_MCP_EXECUTE not enabled"}
        mgr = get_mcp_manager()
        await mgr.discover_all(root=self.config.tool_metadata_root, timeout_s=timeout_s)
        ids = [t.id for t in self.registry.as_list()]
        exe = mgr.reconcile_registry_ids(ids)
        marked = self.apply_mcp_reconcile(exe)
        return {
            "skipped": False,
            "tools_advertised": sum(len(v) for v in mgr.discovered_by_server.values()),
            "tools_executable": marked,
            "catalog_hash": mgr.catalog_hash,
            **mgr.status(),
        }

    def observe_outcome(self, agent_id: str, tool_id: str, *, success: bool, latency_ms: float = 0.0) -> None:
        tool = self.registry.get_optional(tool_id)
        if success:
            self.history.record_success(agent_id, tool or tool_id, latency_ms=latency_ms)
            if tool:
                self.registry.update(
                    tool_id,
                    success_rate=min(1.0, tool.success_rate * 0.9 + 0.1),
                    recent_usage=tool.recent_usage + 1,
                    popularity=tool.popularity + 0.01,
                )
        else:
            self.history.record_failure(agent_id, tool or tool_id)
            if tool:
                self.registry.update(
                    tool_id,
                    failure_rate=min(1.0, tool.failure_rate * 0.9 + 0.1),
                    success_rate=max(0.0, tool.success_rate * 0.95),
                )
        self.reranker.rl_hook.observe_reward(tool_id, 1.0 if success else 0.0)

    def benchmark(self, cases: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        from .benchmarks.runner import run_router_benchmark

        return run_router_benchmark(self, cases=cases)

    def shutdown(self) -> None:
        if self.sync:
            self.sync.stop()
        self.embedder.shutdown()
