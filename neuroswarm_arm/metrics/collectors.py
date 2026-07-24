"""Pull collectors — psutil hardware + optional Performix/PMU."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .registry import MetricRegistry

logger = logging.getLogger(__name__)


@runtime_checkable
class MetricCollector(Protocol):
    def collect(self) -> None: ...

    def start(self) -> None: ...

    def stop(self) -> None: ...


class PsutilCollector:
    """Periodic process/system metrics via psutil (graceful if missing)."""

    def __init__(
        self,
        registry: MetricRegistry,
        *,
        interval_s: float = 5.0,
    ) -> None:
        self.registry = registry
        self.interval_s = max(0.5, float(interval_s))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._psutil = None
        try:
            import psutil

            self._psutil = psutil
        except Exception:
            self._psutil = None

    def collect(self) -> None:
        if self._psutil is None:
            return
        proc = self._psutil.Process(os.getpid())
        with proc.oneshot():
            mem = proc.memory_info()
            self.registry.set("nexus_memory_rss_bytes", float(mem.rss))
            self.registry.set("nexus_hw_memory_usage_bytes", float(mem.rss))
            self.registry.set("nexus_hw_thread_count", float(proc.num_threads()))
            try:
                ctx = proc.num_ctx_switches()
                self.registry.set(
                    "nexus_hw_context_switches_total",
                    float(ctx.voluntary + ctx.involuntary),
                )
            except Exception:
                pass
        try:
            cpu = self._psutil.cpu_percent(interval=None) / 100.0
            self.registry.set("nexus_hw_cpu_usage", float(cpu))
        except Exception:
            pass
        try:
            freq = self._psutil.cpu_freq()
            if freq is not None:
                self.registry.set("nexus_hw_cpu_frequency_hz", float(freq.current) * 1_000_000.0)
        except Exception:
            pass

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return

        def _loop() -> None:
            while not self._stop.is_set():
                try:
                    self.collect()
                except Exception as exc:
                    logger.debug("psutil collect failed: %s", exc)
                self._stop.wait(self.interval_s)

        self._stop.clear()
        self._thread = threading.Thread(target=_loop, name="rmf-psutil", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None


class PerformixCollector:
    """Read Performix/PMU snapshot JSON; zero metrics when unavailable."""

    def __init__(
        self,
        registry: MetricRegistry,
        *,
        path: str | Path = "work/performix/snapshot.json",
        interval_s: float = 5.0,
        enabled: bool = False,
    ) -> None:
        self.registry = registry
        self.path = Path(path)
        self.interval_s = max(0.5, float(interval_s))
        self.enabled = enabled
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def collect(self) -> None:
        if not self.enabled or not self.path.exists():
            self.registry.set("nexus_performix_available", 0.0)
            self.registry.set("nexus_performix_cycles", 0.0)
            self.registry.set("nexus_performix_instructions", 0.0)
            self.registry.set("nexus_performix_ipc", 0.0)
            self.registry.set("nexus_performix_cache_misses", 0.0)
            self.registry.set("nexus_performix_branch_misses", 0.0)
            self.registry.set("nexus_performix_snapshot_age_seconds", 0.0)
            return
        try:
            age = max(0.0, time.time() - self.path.stat().st_mtime)
            self.registry.set("nexus_performix_snapshot_age_seconds", age)
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.debug("performix snapshot read failed: %s", exc)
            self.registry.set("nexus_performix_available", 0.0)
            self.registry.set("nexus_performix_snapshot_age_seconds", 0.0)
            return
        self.registry.set("nexus_performix_available", 1.0)
        cycles = float(data.get("cycles") or data.get("cpu_cycles") or 0.0)
        instr = float(data.get("instructions") or data.get("retired_instructions") or 0.0)
        self.registry.set("nexus_performix_cycles", cycles)
        self.registry.set("nexus_performix_instructions", instr)
        ipc = float(data.get("ipc") or (instr / cycles if cycles > 0 else 0.0))
        self.registry.set("nexus_performix_ipc", ipc)
        self.registry.set(
            "nexus_performix_cache_misses",
            float(data.get("cache_misses") or data.get("l2_misses") or 0.0),
        )
        self.registry.set(
            "nexus_performix_branch_misses",
            float(data.get("branch_misses") or 0.0),
        )
        metrics = data.get("metrics") if isinstance(data.get("metrics"), dict) else {}
        self.registry.set(
            "nexus_performix_hotspot_top_pct",
            float(metrics.get("hotspot_top_pct") or data.get("hotspot_pct") or 0.0),
        )
        hotspots = data.get("hotspots") or []
        self.registry.set(
            "nexus_performix_hotspot_count",
            float(len(hotspots) if isinstance(hotspots, list) else 0),
        )
        if isinstance(hotspots, list):
            for item in hotspots[:10]:
                if not isinstance(item, dict):
                    continue
                fn = str(item.get("function") or item.get("name") or item.get("symbol") or "unknown")[:96]
                pct = item.get("pct") or item.get("percent") or item.get("self")
                if pct is None:
                    continue
                try:
                    self.registry.set(
                        "nexus_performix_hotspot_pct",
                        float(pct),
                        labels={"function": fn},
                    )
                except Exception:
                    continue
        topdown = data.get("topdown") or data.get("microarch") or {}
        if isinstance(topdown, dict):
            self.registry.set(
                "nexus_performix_frontend_bound",
                float(topdown.get("frontend_bound") or topdown.get("frontend") or 0.0),
            )
            self.registry.set(
                "nexus_performix_backend_bound",
                float(topdown.get("backend_bound") or topdown.get("backend") or 0.0),
            )
        self.registry.set(
            "nexus_performix_pmu_available",
            float(data.get("pmu_available") if data.get("pmu_available") is not None else (1.0 if cycles > 0 else 0.0)),
        )
        pmu = data.get("pmu_events") or data.get("events") or {}
        if isinstance(pmu, dict):
            for event, value in pmu.items():
                try:
                    self.registry.set(
                        "nexus_performix_pmu_events",
                        float(value),
                        labels={"event": str(event)[:64]},
                    )
                except Exception:
                    continue
        hotspot = data.get("hotspot_percent")
        if hotspot is not None:
            self.registry.set("nexus_hw_cache_utilization", float(hotspot) / 100.0)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return

        def _loop() -> None:
            while not self._stop.is_set():
                try:
                    self.collect()
                except Exception as exc:
                    logger.debug("performix collect failed: %s", exc)
                self._stop.wait(self.interval_s)

        self._stop.clear()
        self._thread = threading.Thread(target=_loop, name="rmf-performix", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None


class NumaCollector:
    """Publish honest NUMA topology gauges (Axion = single UMA / cross_numa=0)."""

    def __init__(
        self,
        registry: MetricRegistry,
        *,
        interval_s: float = 15.0,
    ) -> None:
        self.registry = registry
        self.interval_s = max(2.0, float(interval_s))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def collect(self) -> None:
        try:
            from neuroswarm_arm.runtime.haoe.topology.numa_status import publish_numa_metrics

            publish_numa_metrics(self.registry)
        except Exception as exc:
            logger.debug("numa collect failed: %s", exc)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return

        def _loop() -> None:
            while not self._stop.is_set():
                try:
                    self.collect()
                except Exception as exc:
                    logger.debug("numa collect failed: %s", exc)
                self._stop.wait(self.interval_s)

        self._stop.clear()
        self.collect()
        self._thread = threading.Thread(target=_loop, name="rmf-numa", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None


class CollectorHub:
    def __init__(self) -> None:
        self._collectors: list[MetricCollector] = []

    def add(self, collector: MetricCollector) -> None:
        self._collectors.append(collector)

    def start(self) -> None:
        for c in self._collectors:
            c.start()

    def stop(self) -> None:
        for c in self._collectors:
            c.stop()

    def collect_once(self) -> None:
        for c in self._collectors:
            c.collect()
