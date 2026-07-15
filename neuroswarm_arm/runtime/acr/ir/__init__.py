"""Compiler-style intermediate representations for Adaptive Context Runtime."""

from neuroswarm_arm.runtime.acr.ir.bundles import KnowledgeBundle, KnowledgeItem, MemoryBundle, MemoryItem
from neuroswarm_arm.runtime.acr.ir.cache_key import ContextCacheKey
from neuroswarm_arm.runtime.acr.ir.context import (
    AssembledSection,
    ContextGraph,
    ContextSnapshot,
    ContextVersion,
    FinalStructuredPrompt,
    ProvenanceRef,
)
from neuroswarm_arm.runtime.acr.ir.plan import (
    AssemblyPlan,
    CompressionPass,
    CompressionPlan,
    RetrievalExecutionPlan,
    RetrievalSource,
    RetrievalStep,
)
from neuroswarm_arm.runtime.acr.ir.requirement import (
    ContextRequirementGraph,
    RequirementKind,
    RequirementNode,
)
from neuroswarm_arm.runtime.acr.ir.stats import CompressionMetrics, ContextStatistics

__all__ = [
    "AssembledSection",
    "AssemblyPlan",
    "CompressionMetrics",
    "CompressionPass",
    "CompressionPlan",
    "ContextCacheKey",
    "ContextGraph",
    "ContextRequirementGraph",
    "ContextSnapshot",
    "ContextStatistics",
    "ContextVersion",
    "FinalStructuredPrompt",
    "KnowledgeBundle",
    "KnowledgeItem",
    "MemoryBundle",
    "MemoryItem",
    "ProvenanceRef",
    "RequirementKind",
    "RequirementNode",
    "RetrievalExecutionPlan",
    "RetrievalSource",
    "RetrievalStep",
]
