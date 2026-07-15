"""ACR ports — dependency injection / replaceability."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from neuroswarm_arm.runtime.acr.ir.bundles import KnowledgeBundle, MemoryBundle
from neuroswarm_arm.runtime.acr.ir.context import ContextSnapshot
from neuroswarm_arm.runtime.acr.ir.plan import (
    AssemblyPlan,
    CompressionPlan,
    RetrievalExecutionPlan,
)
from neuroswarm_arm.runtime.acr.ir.requirement import ContextRequirementGraph
from neuroswarm_arm.runtime.acr.ir.stats import CompressionMetrics


@runtime_checkable
class IUnderstandingEngine(Protocol):
    def understand(
        self,
        query: str,
        *,
        request_id: str,
        agent_role: str = "architect",
        owner: str = "default",
        metadata: dict[str, Any] | None = None,
    ) -> ContextRequirementGraph: ...


@runtime_checkable
class IContextPlanner(Protocol):
    def plan(
        self,
        graph: ContextRequirementGraph,
        *,
        token_budget: int = 2000,
        latency_budget_ms: float = 200.0,
        cost_budget: float = 0.01,
    ) -> RetrievalExecutionPlan: ...


@runtime_checkable
class IMemoryRuntimeAdapter(Protocol):
    def retrieve(self, plan: RetrievalExecutionPlan, owner: str = "default") -> MemoryBundle: ...


@runtime_checkable
class IKnowledgeRuntimeAdapter(Protocol):
    def retrieve(
        self,
        plan: RetrievalExecutionPlan,
        *,
        agent_profile: str = "architect",
        tool_names: list[str] | None = None,
    ) -> KnowledgeBundle: ...


@runtime_checkable
class IScoringEngine(Protocol):
    def score_memory(self, bundle: MemoryBundle, graph: ContextRequirementGraph) -> MemoryBundle: ...

    def score_knowledge(
        self, bundle: KnowledgeBundle, graph: ContextRequirementGraph
    ) -> KnowledgeBundle: ...


@runtime_checkable
class ICompressionEngine(Protocol):
    def compress(
        self,
        memory: MemoryBundle,
        knowledge: KnowledgeBundle,
        plan: CompressionPlan,
        graph: ContextRequirementGraph,
    ) -> tuple[MemoryBundle, KnowledgeBundle, CompressionMetrics]: ...


@runtime_checkable
class IAssemblyEngine(Protocol):
    def assemble(
        self,
        memory: MemoryBundle,
        knowledge: KnowledgeBundle,
        plan: AssemblyPlan,
        *,
        request_id: str,
        plan_id: str,
        graph: ContextRequirementGraph,
        tool_prompt_block: str = "",
    ) -> ContextSnapshot: ...


@runtime_checkable
class IContextCache(Protocol):
    def get(self, key_digest: str) -> ContextSnapshot | None: ...

    def put(self, key_digest: str, snapshot: ContextSnapshot, *, tier: str = "hot") -> None: ...

    def invalidate(self, *, prefix: str = "", version_hash: str = "") -> int: ...


@runtime_checkable
class IContextVersioning(Protocol):
    def stamp(self, snapshot: ContextSnapshot) -> ContextSnapshot: ...

    def diff(self, a: ContextSnapshot, b: ContextSnapshot) -> dict[str, Any]: ...

    def rollback(self, version_id: str) -> ContextSnapshot | None: ...


@runtime_checkable
class IEvolutionEngine(Protocol):
    def record(
        self,
        snapshot: ContextSnapshot,
        *,
        success: bool,
        cost: float = 0.0,
        latency_ms: float = 0.0,
        owner: str = "default",
    ) -> list[str]: ...


@runtime_checkable
class IHardwareTopology(Protocol):
    def discover(self) -> Any: ...

    def numa_nodes(self) -> list[int] | None: ...

    def prefer_local(self, size_bytes: int = 0) -> Any: ...
