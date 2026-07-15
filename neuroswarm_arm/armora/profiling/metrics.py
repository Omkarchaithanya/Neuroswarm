"""Metric aggregation helpers for RPF samples."""

from __future__ import annotations

from typing import Iterable

from .schemas import MetricBatch, MetricSample


def merge_batches(*batches: MetricBatch) -> dict[str, float]:
    out: dict[str, float] = {}
    for batch in batches:
        for sample in batch.samples:
            out[sample.name] = float(sample.value)
    return out


def get_float(values: dict[str, float], *keys: str, default: float = 0.0) -> float:
    for key in keys:
        if key in values:
            return float(values[key])
    return default


def affinity_from_values(values: dict[str, float]) -> list[int]:
    items: list[tuple[int, int]] = []
    for k, v in values.items():
        if k.startswith("cpu.affinity."):
            try:
                idx = int(k.rsplit(".", 1)[-1])
                items.append((idx, int(v)))
            except Exception:
                continue
    items.sort()
    return [c for _, c in items]


def flatten_samples(samples: Iterable[MetricSample]) -> dict[str, float]:
    return {s.name: float(s.value) for s in samples}


def heuristic_recommendations(values: dict[str, float]) -> list[str]:
    recs: list[str] = []
    ipc = get_float(values, "hardware.ipc")
    if 0 < ipc < 0.8:
        recs.append("Low IPC detected — inspect cache/branch stalls and vectorization")
    cache_misses = get_float(values, "hardware.cache_misses")
    cache_refs = get_float(values, "hardware.cache_references")
    if cache_refs > 0 and (cache_misses / cache_refs) > 0.2:
        recs.append("High cache miss ratio — consider locality / KV tier placement")
    cpu = get_float(values, "cpu.usage_percent")
    if cpu > 90:
        recs.append("Sustained high CPU — review thread affinity and batching")
    rss = get_float(values, "memory.rss_bytes")
    if rss > 8 * 1024**3:
        recs.append("High RSS — review MAKS eviction / context compression")
    return recs
