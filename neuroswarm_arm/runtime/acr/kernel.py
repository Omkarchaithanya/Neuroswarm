"""Adaptive Context Runtime kernel — orchestrates the context pipeline."""

from __future__ import annotations

import hashlib
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from neuroswarm_arm.runtime.acr.assembly import AssemblyEngine
from neuroswarm_arm.runtime.acr.cache import ContextCache
from neuroswarm_arm.runtime.acr.compression import CompressionEngine
from neuroswarm_arm.runtime.acr.config import ACRConfig
from neuroswarm_arm.runtime.acr.evolution import EvolutionEngine
from neuroswarm_arm.runtime.acr.hardware import HardwareTopology
from neuroswarm_arm.runtime.acr.ir.cache_key import ContextCacheKey
from neuroswarm_arm.runtime.acr.ir.context import ContextSnapshot
from neuroswarm_arm.runtime.acr.ir.plan import AssemblyPlan, CompressionPlan
from neuroswarm_arm.runtime.acr.ir.stats import ContextStatistics
from neuroswarm_arm.runtime.acr.knowledge import KnowledgeRuntimeAdapter
from neuroswarm_arm.runtime.acr.memory import MemoryRuntimeAdapter
from neuroswarm_arm.runtime.acr.metrics import ACRMetrics
from neuroswarm_arm.runtime.acr.planner import ContextPlanner
from neuroswarm_arm.runtime.acr.plugins import PluginRegistry
from neuroswarm_arm.runtime.acr.scoring import ScoringEngine
from neuroswarm_arm.runtime.acr.understanding import UnderstandingEngine
from neuroswarm_arm.runtime.acr.versioning import ContextVersioning


class AdaptiveContextRuntime:
    """Context Operating System — smallest high-information context for ARM inference."""

    def __init__(
        self,
        config: ACRConfig,
        *,
        memory: Any | None = None,
        okf: Any | None = None,
        understanding: UnderstandingEngine | None = None,
        planner: ContextPlanner | None = None,
        memory_adapter: MemoryRuntimeAdapter | None = None,
        knowledge_adapter: KnowledgeRuntimeAdapter | None = None,
        scoring: ScoringEngine | None = None,
        compression: CompressionEngine | None = None,
        assembly: AssemblyEngine | None = None,
        cache: ContextCache | None = None,
        versioning: ContextVersioning | None = None,
        evolution: EvolutionEngine | None = None,
        hardware: HardwareTopology | None = None,
        metrics: ACRMetrics | None = None,
        plugins: PluginRegistry | None = None,
    ) -> None:
        self.config = config
        self.metrics = metrics or ACRMetrics()
        self.hardware = hardware or HardwareTopology()
        placement = self.hardware.prefer_local()
        self.understanding = understanding or UnderstandingEngine()
        self.planner = planner or ContextPlanner()
        self.memory_adapter = memory_adapter or MemoryRuntimeAdapter(memory)
        self.knowledge_adapter = knowledge_adapter or KnowledgeRuntimeAdapter(okf)
        self.scoring = scoring or ScoringEngine()
        self.compression = compression or CompressionEngine()
        self.assembly = assembly or AssemblyEngine()
        self.cache = cache or ContextCache(
            max_entries=config.cache_max_entries,
            ttl_s=config.cache_ttl_s,
            numa_node=placement.numa_node,
        )
        self.versioning = versioning or ContextVersioning()
        self.evolution = evolution or EvolutionEngine(memory=memory)
        self.plugins = plugins or PluginRegistry()
        self._memory = memory
        self._okf = okf

    @property
    def enabled(self) -> bool:
        return bool(self.config.enabled)

    def build_context(
        self,
        query: str,
        *,
        owner: str = "default",
        agent_role: str = "architect",
        request_id: str = "",
        tool_names: list[str] | None = None,
        tool_prompt_block: str = "",
        token_budget: int | None = None,
        metadata: dict[str, Any] | None = None,
        use_cache: bool = True,
    ) -> ContextSnapshot:
        """Full pipeline: understand → plan → retrieve → score → compress → assemble → version."""
        if not self.enabled:
            return ContextSnapshot(request_id=request_id or "disabled", prompt="")

        t_all = time.perf_counter()
        budget = token_budget if token_budget is not None else self.config.token_budget
        fp = hashlib.sha256(
            f"{query}|{owner}|{agent_role}|{budget}|{','.join(tool_names or [])}".encode()
        ).hexdigest()[:24]

        cache_key = ContextCacheKey(
            tier="hot",
            request_fingerprint=fp,
            owner=owner,
            agent_role=agent_role,
        )
        cache_digest = cache_key.digest()

        if use_cache and self.config.cache_enabled:
            cached = self.cache.get(cache_digest)
            if cached is not None:
                self.metrics.inc("cache_hit")
                self.metrics.set_gauge("cache_hit_ratio", self.cache.hit_ratio())
                return cached
            self.metrics.inc("cache_miss")

        stats = ContextStatistics()
        placement = self.hardware.prefer_local()
        stats.numa_node = placement.numa_node

        with self.metrics.timed("understanding"):
            t0 = time.perf_counter()
            graph = self.understanding.understand(
                query,
                request_id=request_id or fp,
                agent_role=agent_role,
                owner=owner,
                metadata=metadata,
            )
            stats.planning_latency_ms += (time.perf_counter() - t0) * 1000.0

        with self.metrics.timed("planning"):
            t0 = time.perf_counter()
            plan = self.planner.plan(
                graph,
                token_budget=budget,
                latency_budget_ms=self.config.latency_budget_ms,
                cost_budget=self.config.cost_budget,
                progressive=self.config.progressive,
            )
            stats.planning_latency_ms += (time.perf_counter() - t0) * 1000.0

        with self.metrics.timed("retrieval"):
            t0 = time.perf_counter()
            mem_bundle, know_bundle = self._retrieve(plan, owner=owner, agent_role=agent_role, tool_names=tool_names)
            stats.retrieval_latency_ms = (time.perf_counter() - t0) * 1000.0

        stats.input_tokens = mem_bundle.total_tokens + know_bundle.total_tokens
        stats.memory_items = len(mem_bundle.items)
        stats.knowledge_items = len(know_bundle.items)

        with self.metrics.timed("scoring"):
            mem_bundle = self.scoring.score_memory(mem_bundle, graph)
            know_bundle = self.scoring.score_knowledge(know_bundle, graph)

        comp_plan = CompressionPlan(
            token_budget=budget,
            min_importance=self.config.min_importance,
        )
        with self.metrics.timed("compression"):
            t0 = time.perf_counter()
            mem_bundle, know_bundle, comp_metrics = self.compression.compress(
                mem_bundle, know_bundle, comp_plan, graph
            )
            stats.compression_latency_ms = (time.perf_counter() - t0) * 1000.0
            stats.compression = comp_metrics

        asm_plan = AssemblyPlan(token_budget=budget, stable_prefix=self.config.stable_prefix)
        with self.metrics.timed("assembly"):
            t0 = time.perf_counter()
            snapshot = self.assembly.assemble(
                mem_bundle,
                know_bundle,
                asm_plan,
                request_id=graph.request_id,
                plan_id=plan.plan_id,
                graph=graph,
                tool_prompt_block=tool_prompt_block,
                stats=stats,
            )
            stats.assembly_latency_ms = (time.perf_counter() - t0) * 1000.0

        stats.requirement_coverage = comp_metrics.information_retained
        stats.total_latency_ms = (time.perf_counter() - t_all) * 1000.0
        snapshot.stats = stats

        snapshot = self.versioning.stamp(snapshot)
        self.metrics.inc("build_context")
        self.metrics.set_gauge("last_compression_ratio", comp_metrics.compression_ratio)
        self.metrics.set_gauge("last_token_reduction", comp_metrics.token_reduction)
        self.metrics.set_gauge("last_information_retained", comp_metrics.information_retained)
        self.metrics.set_gauge("cache_hit_ratio", self.cache.hit_ratio())

        if use_cache and self.config.cache_enabled:
            self.cache.put(
                cache_digest,
                snapshot,
                tier="hot",
                version_hash=snapshot.version.content_hash,
                deps={p.ref_id for p in snapshot.provenance if p.ref_id},
            )
        return snapshot

    def evolve(
        self,
        snapshot: ContextSnapshot,
        *,
        success: bool,
        cost: float = 0.0,
        latency_ms: float = 0.0,
        owner: str = "default",
    ) -> list[str]:
        with self.metrics.timed("evolution"):
            recs = self.evolution.record(
                snapshot, success=success, cost=cost, latency_ms=latency_ms, owner=owner
            )
        self.metrics.inc("evolution_total")
        return recs

    def health(self) -> dict[str, Any]:
        topo = self.hardware.discover()
        return {
            "enabled": self.enabled,
            "cache": self.cache.stats(),
            "numa_nodes": topo.numa_nodes,
            "arch": topo.arch,
            "metrics": self.metrics.snapshot(),
        }

    def prometheus_text(self) -> str:
        return self.metrics.prometheus_text()

    def _retrieve(self, plan, *, owner: str, agent_role: str, tool_names: list[str] | None):
        if self.config.parallel_retrieve:
            workers = self.hardware.pin_workers(2)
            with ThreadPoolExecutor(max_workers=workers) as pool:
                fut_m = pool.submit(self.memory_adapter.retrieve, plan, owner)
                fut_k = pool.submit(
                    self.knowledge_adapter.retrieve,
                    plan,
                    agent_profile=agent_role,
                    tool_names=tool_names,
                )
                return fut_m.result(), fut_k.result()
        mem = self.memory_adapter.retrieve(plan, owner=owner)
        know = self.knowledge_adapter.retrieve(
            plan, agent_profile=agent_role, tool_names=tool_names
        )
        return mem, know
