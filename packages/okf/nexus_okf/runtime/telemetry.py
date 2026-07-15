from __future__ import annotations

from dataclasses import dataclass, field

try:
    from prometheus_client import Counter, Histogram, CollectorRegistry, REGISTRY
except Exception:  # pragma: no cover
    Counter = None  # type: ignore
    Histogram = None  # type: ignore
    CollectorRegistry = None  # type: ignore
    REGISTRY = None  # type: ignore

_PROM_Q = None
_PROM_HIT = None
_PROM_LAT = None


def _prom():
    global _PROM_Q, _PROM_HIT, _PROM_LAT
    if Counter is None:
        return None, None, None
    if _PROM_Q is None:
        try:
            _PROM_Q = Counter("okf_queries_total", "OKF queries")
            _PROM_HIT = Counter("okf_cache_hits_total", "OKF cache hits")
            _PROM_LAT = Histogram("okf_query_latency_ms", "OKF query latency ms")
        except ValueError:
            # Already registered in this process
            if REGISTRY is not None:
                _PROM_Q = REGISTRY._names_to_collectors.get("okf_queries_total")
                _PROM_HIT = REGISTRY._names_to_collectors.get("okf_cache_hits_total")
                _PROM_LAT = REGISTRY._names_to_collectors.get("okf_query_latency_ms")
    return _PROM_Q, _PROM_HIT, _PROM_LAT


@dataclass
class OKFMetrics:
    queries: int = 0
    cache_hits: int = 0
    tokens_total: int = 0
    latency_ms: list[float] = field(default_factory=list)

    def record_query(self, ctx: object) -> None:
        self.queries += 1
        cache_hit = bool(getattr(ctx, "cache_hit", False))
        if cache_hit:
            self.cache_hits += 1
        self.tokens_total += int(getattr(ctx, "tokens_used", 0) or 0)
        metrics = getattr(ctx, "metrics", {}) or {}
        lat = float(metrics.get("latency_ms", 0.0))
        self.latency_ms.append(lat)
        q, hit, hist = _prom()
        if q is not None:
            try:
                q.inc()
            except Exception:
                pass
        if cache_hit and hit is not None:
            try:
                hit.inc()
            except Exception:
                pass
        if hist is not None and lat:
            try:
                hist.observe(lat)
            except Exception:
                pass

    def snapshot(self) -> dict[str, float]:
        return {
            "queries": float(self.queries),
            "cache_hits": float(self.cache_hits),
            "cache_hit_ratio": (self.cache_hits / self.queries) if self.queries else 0.0,
            "tokens_total": float(self.tokens_total),
            "latency_p50_ms": sorted(self.latency_ms)[len(self.latency_ms) // 2]
            if self.latency_ms
            else 0.0,
        }
