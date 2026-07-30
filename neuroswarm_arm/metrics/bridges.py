"""Plane bridges — publish Budget/RCIS/HAOE/DIPA/MAKS/AWPP/AROP into RMF."""

from __future__ import annotations

import logging
from typing import Any, Callable, Mapping

from .lifecycle import RuntimeMetricsFramework

logger = logging.getLogger(__name__)


class PlaneMetricBridge:
    """Adapter that pulls plane telemetry into the RMF registry on scrape/flush."""

    def __init__(self, rmf: RuntimeMetricsFramework) -> None:
        self.rmf = rmf

    def source_from_callable(self, fn: Callable[[], str]) -> None:
        self.rmf.register_source(fn)

    def publish_counter(self, name: str, value: float, labels: Mapping[str, str] | None = None) -> None:
        self.rmf.inc(name, value, labels=dict(labels or {}))

    def publish_gauge(self, name: str, value: float, labels: Mapping[str, str] | None = None) -> None:
        self.rmf.set(name, value, labels=dict(labels or {}))

    def wire_budget(self, budget_service: Any) -> None:
        def _export() -> str:
            try:
                if hasattr(budget_service, "export_prometheus"):
                    return str(budget_service.export_prometheus())
            except Exception as exc:
                logger.debug("budget bridge export failed: %s", exc)
            return ""

        self.source_from_callable(_export)
        try:
            snap = getattr(budget_service, "telemetry", None)
            if snap is not None and hasattr(snap, "snapshot"):
                data = snap.snapshot()
                if isinstance(data, Mapping):
                    for key, value in data.items():
                        try:
                            self.rmf.set(str(key), float(value))
                        except Exception:
                            continue
        except Exception:
            pass

    def wire_rcis(self, rcis: Any) -> None:
        def _export() -> str:
            try:
                if hasattr(rcis, "export_prometheus"):
                    return str(rcis.export_prometheus())
            except Exception as exc:
                logger.debug("rcis bridge export failed: %s", exc)
            return ""

        self.source_from_callable(_export)

    def wire_haoe(self, haoe: Any) -> None:
        metrics = getattr(haoe, "metrics", None) or getattr(getattr(haoe, "telemetry", None), "metrics", None)
        if metrics is None:
            return

        def _pull() -> str:
            try:
                local = getattr(metrics, "local", None)
                if local is not None and hasattr(local, "snapshot"):
                    data = local.snapshot()
                    if isinstance(data, Mapping):
                        for key, value in data.items():
                            name = str(key)
                            try:
                                if name.endswith("_total") or "steal" in name:
                                    self.rmf.set(name, float(value))
                                else:
                                    self.rmf.set(name, float(value))
                                # Map known HAOE names into nexus_* 
                                if name == "haoe_queue_depth":
                                    self.rmf.set("nexus_haoe_queue_depth", float(value))
                                elif name == "haoe_worker_utilization":
                                    self.rmf.set("nexus_haoe_worker_utilization", float(value))
                                elif name == "haoe_steal_total":
                                    self.rmf.set("nexus_haoe_steal_total", float(value))
                                elif name == "haoe_scheduling_latency_ms":
                                    self.rmf.observe(
                                        "nexus_haoe_scheduler_latency_seconds",
                                        float(value) / 1000.0,
                                    )
                            except Exception:
                                continue
                if hasattr(metrics, "export_prometheus"):
                    return str(metrics.export_prometheus())
            except Exception as exc:
                logger.debug("haoe bridge failed: %s", exc)
            return ""

        self.source_from_callable(_pull)

    def wire_dipa(self, dipa: Any) -> None:
        telemetry = getattr(dipa, "telemetry", None)
        metrics = getattr(telemetry, "metrics", None) if telemetry is not None else getattr(dipa, "metrics", None)
        if metrics is None:
            return

        def _pull() -> str:
            try:
                snap = None
                if hasattr(metrics, "snapshot"):
                    snap = metrics.snapshot()
                elif hasattr(metrics, "local") and hasattr(metrics.local, "snapshot"):
                    snap = metrics.local.snapshot()
                if isinstance(snap, Mapping):
                    for key, value in snap.items():
                        name = str(key)
                        try:
                            self.rmf.set(name, float(value))
                            if "prefill" in name and "ms" in name:
                                self.rmf.observe("nexus_dipa_prefill_latency_seconds", float(value) / 1000.0)
                            elif "decode" in name and "ms" in name:
                                self.rmf.observe("nexus_dipa_decode_latency_seconds", float(value) / 1000.0)
                            elif name in {
                                "dipa_tokens_per_sec",
                                "dipa_llama_predicted_per_second",
                                "dipa_decode_tps",
                            }:
                                self.rmf.set("nexus_tokens_per_second", float(value))
                        except Exception:
                            continue
                if hasattr(metrics, "export_prometheus"):
                    return str(metrics.export_prometheus())
            except Exception as exc:
                logger.debug("dipa bridge failed: %s", exc)
            return ""

        self.source_from_callable(_pull)

    def wire_maks(self, maks: Any) -> None:
        metrics = getattr(maks, "metrics", None)
        if metrics is None:
            return

        def _pull() -> str:
            try:
                if hasattr(metrics, "snapshot"):
                    snap = metrics.snapshot()
                    if isinstance(snap, Mapping):
                        for key, value in snap.items():
                            try:
                                self.rmf.set(str(key), float(value))
                                if "hit" in str(key):
                                    self.rmf.inc("nexus_kv_cache_hits_total", 0.0)
                                if "evict" in str(key):
                                    self.rmf.set("nexus_kv_cache_evictions_total", float(value))
                                if "bytes" in str(key) or "size" in str(key):
                                    self.rmf.set("nexus_kv_cache_bytes", float(value))
                            except Exception:
                                continue
                if hasattr(metrics, "prometheus_text"):
                    return str(metrics.prometheus_text())
                if hasattr(metrics, "export_prometheus"):
                    return str(metrics.export_prometheus())
            except Exception as exc:
                logger.debug("maks bridge failed: %s", exc)
            return ""

        self.source_from_callable(_pull)

    def wire_awpp(self, awpp: Any) -> None:
        metrics = getattr(awpp, "metrics", None)
        if metrics is None:
            return

        def _pull() -> str:
            try:
                if hasattr(metrics, "snapshot"):
                    snap = metrics.snapshot()
                    if isinstance(snap, Mapping):
                        for key, value in snap.items():
                            try:
                                self.rmf.set(str(key), float(value))
                            except Exception:
                                continue
                if hasattr(metrics, "export_prometheus"):
                    return str(metrics.export_prometheus())
            except Exception as exc:
                logger.debug("awpp bridge failed: %s", exc)
            return ""

        self.source_from_callable(_pull)

    def wire_kv(self, kv_runtime: Any) -> None:
        telemetry = getattr(kv_runtime, "telemetry", None)
        if telemetry is None:
            return

        def _pull() -> str:
            try:
                if hasattr(telemetry, "export_prometheus"):
                    return str(telemetry.export_prometheus())
            except Exception as exc:
                logger.debug("kv bridge failed: %s", exc)
            return ""

        self.source_from_callable(_pull)

    def wire_acr(self, acr_runtime: Any) -> None:
        def _pull() -> str:
            try:
                if hasattr(acr_runtime, "prometheus_text"):
                    return str(acr_runtime.prometheus_text())
            except Exception as exc:
                logger.debug("acr bridge failed: %s", exc)
            return ""

        self.source_from_callable(_pull)


class RMFObservationProvider:
    """AROP ObservationProvider reading aggregated RMF snapshots."""

    name = "rmf"

    def __init__(self, rmf: RuntimeMetricsFramework) -> None:
        self.rmf = rmf

    def collect(self) -> dict[str, float]:
        return self.rmf.registry.aggregate_values()

    def snapshot(self) -> dict[str, float]:
        return self.collect()

    def metrics(self) -> dict[str, float]:
        return self.collect()

    def health(self) -> dict[str, Any]:
        snap = self.rmf.registry.snapshot()
        return {
            "ok": True,
            "provider": self.name,
            "series": len(snap.series),
            "dropped_labels": snap.dropped_labels,
            "cardinality_rejects": snap.cardinality_rejects,
        }
