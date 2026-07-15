"""ContextStatistics and compression metrics."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class CompressionMetrics:
    """Measurable compression — no fixed percentage targets."""

    input_tokens: int = 0
    output_tokens: int = 0
    compression_ratio: float = 1.0  # output/input; lower is more compressed
    token_reduction: float = 0.0  # 1 - ratio
    information_retained: float = 1.0  # proxy 0..1
    latency_ms: float = 0.0
    confidence: float = 0.0
    passes_applied: list[str] = field(default_factory=list)

    def finalize(self) -> None:
        if self.input_tokens > 0:
            self.compression_ratio = self.output_tokens / self.input_tokens
            self.token_reduction = 1.0 - self.compression_ratio
        else:
            self.compression_ratio = 1.0
            self.token_reduction = 0.0


@dataclass(slots=True)
class ContextStatistics:
    input_tokens: int = 0
    output_tokens: int = 0
    memory_items: int = 0
    knowledge_items: int = 0
    planning_latency_ms: float = 0.0
    retrieval_latency_ms: float = 0.0
    compression_latency_ms: float = 0.0
    assembly_latency_ms: float = 0.0
    total_latency_ms: float = 0.0
    cache_hit: bool = False
    cache_tier: str = ""
    compression: CompressionMetrics = field(default_factory=CompressionMetrics)
    requirement_coverage: float = 0.0
    numa_node: int | None = None
    metadata: dict = field(default_factory=dict)
