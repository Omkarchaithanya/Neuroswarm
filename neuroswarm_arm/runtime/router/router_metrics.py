"""Prometheus-compatible router metrics bridged to global MetricsStore."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from threading import Lock
from time import perf_counter
from typing import Any


ROUTER_METRIC_DEFS: list[tuple[str, str, str]] = [
    ("router_requests_total", "counter", "Total semantic router route() calls."),
    ("router_register_total", "counter", "Tool registration events."),
    ("router_routing_latency_ms", "gauge", "Last end-to-end routing latency ms."),
    ("router_embedding_latency_ms", "gauge", "Last embedding latency ms."),
    ("router_ann_latency_ms", "gauge", "Last ANN search latency ms."),
    ("router_search_latency_ms", "gauge", "Last vector search latency ms (any backend)."),
    ("router_rerank_latency_ms", "gauge", "Last rerank latency ms."),
    ("router_cache_hit_ratio", "gauge", "Embedding cache hit ratio."),
    ("router_embedding_cache_size", "gauge", "Embedding cache entry count."),
    ("router_turbovec_search_ms", "gauge", "Last TurboVec search time ms (only when TurboVec active)."),
    ("router_topk_accuracy_rolling", "gauge", "Rolling top-k accuracy."),
    ("router_avg_confidence", "gauge", "Average routing confidence."),
    ("router_avg_tools_returned", "gauge", "Average tools returned per route."),
    ("router_avg_prompt_reduction", "gauge", "Average prompt size reduction ratio."),
    ("router_avg_token_reduction", "gauge", "Average token reduction ratio."),
    ("router_index_size", "gauge", "Vectors currently indexed."),
    ("router_tools_registered", "gauge", "Tools in registry."),
]


@dataclass
class RouterMetrics:
    bridge: Any | None = None
    lock: Lock = field(default_factory=Lock)
    local: dict[str, float] = field(default_factory=dict)
    cache_hits: float = 0.0
    cache_misses: float = 0.0
    _accuracy: deque[float] = field(default_factory=lambda: deque(maxlen=500))
    _confidence: deque[float] = field(default_factory=lambda: deque(maxlen=500))
    _tools_returned: deque[float] = field(default_factory=lambda: deque(maxlen=500))
    _prompt_reduction: deque[float] = field(default_factory=lambda: deque(maxlen=500))
    _token_reduction: deque[float] = field(default_factory=lambda: deque(maxlen=500))

    def __post_init__(self) -> None:
        for name, mtype, help_text in ROUTER_METRIC_DEFS:
            self.local.setdefault(name, 0.0)
            if self.bridge is not None and hasattr(self.bridge, "describe"):
                try:
                    self.bridge.describe(name, mtype, help_text)
                except Exception:
                    pass

    def inc(self, name: str, value: float = 1.0) -> None:
        with self.lock:
            self.local[name] = self.local.get(name, 0.0) + value
        if self.bridge is not None and hasattr(self.bridge, "inc"):
            try:
                self.bridge.inc(name, value)
            except Exception:
                pass

    def set(self, name: str, value: float) -> None:
        with self.lock:
            self.local[name] = float(value)
        if self.bridge is not None and hasattr(self.bridge, "set"):
            try:
                self.bridge.set(name, float(value))
            except Exception:
                pass

    def observe_cache(self, hit: bool) -> None:
        with self.lock:
            if hit:
                self.cache_hits += 1.0
            else:
                self.cache_misses += 1.0
            total = self.cache_hits + self.cache_misses
            ratio = self.cache_hits / total if total else 0.0
        self.set("router_cache_hit_ratio", ratio)

    def observe_route(
        self,
        *,
        confidence: float,
        tools_returned: int,
        prompt_reduction: float,
        token_reduction: float,
        latency_ms: float,
        accuracy_hit: float | None = None,
    ) -> None:
        with self.lock:
            self._confidence.append(confidence)
            self._tools_returned.append(float(tools_returned))
            self._prompt_reduction.append(prompt_reduction)
            self._token_reduction.append(token_reduction)
            if accuracy_hit is not None:
                self._accuracy.append(accuracy_hit)
            avg_conf = sum(self._confidence) / max(1, len(self._confidence))
            avg_tools = sum(self._tools_returned) / max(1, len(self._tools_returned))
            avg_prompt = sum(self._prompt_reduction) / max(1, len(self._prompt_reduction))
            avg_token = sum(self._token_reduction) / max(1, len(self._token_reduction))
            avg_acc = sum(self._accuracy) / max(1, len(self._accuracy)) if self._accuracy else 0.0
        self.inc("router_requests_total")
        self.set("router_routing_latency_ms", latency_ms)
        self.set("router_avg_confidence", avg_conf)
        self.set("router_avg_tools_returned", avg_tools)
        self.set("router_avg_prompt_reduction", avg_prompt)
        self.set("router_avg_token_reduction", avg_token)
        self.set("router_topk_accuracy_rolling", avg_acc)

    def snapshot(self) -> dict[str, float]:
        with self.lock:
            return dict(self.local)

    def timer(self) -> "_Timer":
        return _Timer()


class _Timer:
    def __init__(self) -> None:
        self._start = perf_counter()

    def ms(self) -> float:
        return (perf_counter() - self._start) * 1000.0
