"""Comparative and analytical report builders for RCIS."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .schemas import RuntimeCostReport, UnitEconomics, safe_div, utcnow


class ComparisonRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    samples: int = 0
    mean_latency_ms: float = 0.0
    mean_memory_bytes: float = 0.0
    mean_cpu_seconds: float = 0.0
    mean_energy_joules: float = 0.0
    mean_cost_usd: float = 0.0
    mean_quality: float = 0.0
    mean_tok_per_s: float = 0.0
    mean_tok_per_watt: float = 0.0
    mean_tok_per_dollar: float = 0.0


class ComparisonReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: str
    rows: list[ComparisonRow] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: utcnow().isoformat())


class SpeculationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accepted: int = 0
    rejected: int = 0
    acceptance_ratio: float = 0.0
    mean_verifier_overhead_ms: float = 0.0
    mean_draft_cost: float = 0.0
    mean_verifier_cost: float = 0.0
    mean_net_savings: float = 0.0
    samples: int = 0


class KVAnalysisReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_hits: int = 0
    total_misses: int = 0
    mean_reuse_ratio: float = 0.0
    mean_memory_saved: float = 0.0
    total_pages_shared: int = 0
    total_migrations: int = 0
    mean_compression_savings: float = 0.0
    samples: int = 0


class EnergyAnalysisReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mean_cpu_seconds: float = 0.0
    mean_joules: float = 0.0
    mean_watts: float = 0.0
    mean_tokens_per_watt: float = 0.0
    mean_carbon_kg: float = 0.0
    samples: int = 0


def _group_means(reports: list[RuntimeCostReport], key_fn: Any) -> list[ComparisonRow]:
    groups: dict[str, list[RuntimeCostReport]] = defaultdict(list)
    for r in reports:
        k = key_fn(r)
        if k:
            groups[str(k)].append(r)
    rows: list[ComparisonRow] = []
    for key, rs in sorted(groups.items()):
        n = float(len(rs))
        rows.append(
            ComparisonRow(
                key=key,
                samples=len(rs),
                mean_latency_ms=safe_div(sum(r.latency_ms for r in rs), n),
                mean_memory_bytes=safe_div(sum(r.peak_memory_bytes for r in rs), n),
                mean_cpu_seconds=safe_div(sum(r.cpu_seconds for r in rs), n),
                mean_energy_joules=safe_div(sum(r.energy_estimate_joules for r in rs), n),
                mean_cost_usd=safe_div(sum(r.estimated_dollars for r in rs), n),
                mean_quality=safe_div(sum(r.quality_score for r in rs), n),
                mean_tok_per_s=safe_div(sum(r.throughput_tokens_per_s for r in rs), n),
                mean_tok_per_watt=safe_div(sum(r.tokens_per_watt for r in rs), n),
                mean_tok_per_dollar=safe_div(sum(r.tokens_per_dollar for r in rs), n),
            )
        )
    return rows


class ReportBuilder:
    """Builds backend / quant / speculation / KV / energy comparative reports."""

    KNOWN_BACKENDS = (
        "llama.cpp",
        "vllm",
        "sglang",
        "rtp-llm",
        "executorch",
        "litert",
    )
    KNOWN_QUANTS = (
        "fp16",
        "bf16",
        "int8",
        "int4",
        "q4_k_m",
        "q5_k_m",
        "q8_0",
    )

    def backend_comparison(self, reports: list[RuntimeCostReport]) -> ComparisonReport:
        return ComparisonReport(
            dimension="backend",
            rows=_group_means(reports, lambda r: r.backend.lower() if r.backend else ""),
        )

    def quantization_comparison(self, reports: list[RuntimeCostReport]) -> ComparisonReport:
        return ComparisonReport(
            dimension="quantization",
            rows=_group_means(
                reports, lambda r: r.quantization.lower() if r.quantization else ""
            ),
        )

    def speculation_analysis(self, reports: list[RuntimeCostReport]) -> SpeculationReport:
        if not reports:
            return SpeculationReport()
        accepted = sum(r.accepted_speculative_tokens for r in reports)
        rejected = sum(r.rejected_speculative_tokens for r in reports)
        n = float(len(reports))
        return SpeculationReport(
            accepted=accepted,
            rejected=rejected,
            acceptance_ratio=safe_div(float(accepted), float(accepted + rejected)),
            mean_verifier_overhead_ms=safe_div(
                sum(r.verifier_overhead_ms for r in reports), n
            ),
            mean_draft_cost=safe_div(sum(r.draft_model_cost_usd for r in reports), n),
            mean_verifier_cost=safe_div(sum(r.verifier_cost_usd for r in reports), n),
            mean_net_savings=safe_div(
                sum(r.speculation_net_savings_usd for r in reports), n
            ),
            samples=len(reports),
        )

    def kv_analysis(self, reports: list[RuntimeCostReport]) -> KVAnalysisReport:
        if not reports:
            return KVAnalysisReport()
        n = float(len(reports))
        return KVAnalysisReport(
            total_hits=sum(r.kv_cache_hits for r in reports),
            total_misses=sum(r.kv_cache_misses for r in reports),
            mean_reuse_ratio=safe_div(sum(r.kv_reuse_ratio for r in reports), n),
            mean_memory_saved=safe_div(sum(r.memory_saved_bytes for r in reports), n),
            total_pages_shared=sum(r.pages_shared for r in reports),
            total_migrations=sum(r.migration_events for r in reports),
            mean_compression_savings=safe_div(
                sum(r.compression_savings_bytes for r in reports), n
            ),
            samples=len(reports),
        )

    def energy_analysis(self, reports: list[RuntimeCostReport]) -> EnergyAnalysisReport:
        if not reports:
            return EnergyAnalysisReport()
        n = float(len(reports))
        return EnergyAnalysisReport(
            mean_cpu_seconds=safe_div(sum(r.cpu_seconds for r in reports), n),
            mean_joules=safe_div(sum(r.energy_estimate_joules for r in reports), n),
            mean_watts=safe_div(sum(r.watts_estimate for r in reports), n),
            mean_tokens_per_watt=safe_div(sum(r.tokens_per_watt for r in reports), n),
            mean_carbon_kg=safe_div(sum(r.estimated_carbon_kg for r in reports), n),
            samples=len(reports),
        )

    def bundle(
        self, reports: list[RuntimeCostReport], economics: UnitEconomics | None = None
    ) -> dict[str, Any]:
        return {
            "backend": self.backend_comparison(reports).model_dump(),
            "quantization": self.quantization_comparison(reports).model_dump(),
            "speculation": self.speculation_analysis(reports).model_dump(),
            "kv": self.kv_analysis(reports).model_dump(),
            "energy": self.energy_analysis(reports).model_dump(),
            "economics": economics.model_dump() if economics else None,
        }
