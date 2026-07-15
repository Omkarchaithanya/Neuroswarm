"""psutil-backed process/system profiler — preferred degrade path."""

from __future__ import annotations

import os
import time
from typing import Any

from ..schemas import (
    CapabilityState,
    MetricBatch,
    ProfileSessionContext,
    ProviderCapabilities,
)
from .base import BaseProfilerProvider, detect_cpu_flags, empty_batch, samples_from_mapping


class PsutilProfilerProvider(BaseProfilerProvider):
    name = "psutil"

    def __init__(self) -> None:
        super().__init__()
        self._psutil: Any | None = None
        self._proc: Any | None = None
        self._start_wall: float = 0.0
        self._peak_rss: float = 0.0
        try:
            import psutil  # type: ignore

            self._psutil = psutil
            self._proc = psutil.Process(os.getpid())
        except Exception:
            self._psutil = None
            self._proc = None

    def capabilities(self) -> ProviderCapabilities:
        ok = self._psutil is not None and self._proc is not None
        return ProviderCapabilities(
            name=self.name,
            available=ok,
            state=CapabilityState.AVAILABLE if ok else CapabilityState.UNAVAILABLE,
            sampling=ok,
            tracing=False,
            cpu=ok,
            memory=ok,
            hardware=False,
            continuous=ok,
            reasons=() if ok else ("psutil not importable",),
            extensions={"cpu_flags": sorted(detect_cpu_flags())},
        )

    def start(self, session: ProfileSessionContext) -> None:
        del session
        self._start_wall = time.monotonic()
        self._peak_rss = 0.0
        if self._proc is not None:
            try:
                self._proc.cpu_percent(interval=None)
            except Exception:
                pass

    def sample(self, session: ProfileSessionContext) -> MetricBatch:
        if self._psutil is None or self._proc is None:
            return empty_batch(self.name, session)
        try:
            with self._proc.oneshot():
                cpu = float(self._proc.cpu_percent(interval=None))
                mem = self._proc.memory_info()
                rss = float(mem.rss)
                vms = float(mem.vms)
                threads = int(self._proc.num_threads())
                try:
                    ctx = self._proc.num_ctx_switches()
                    switches = int(ctx.voluntary) + int(ctx.involuntary)
                except Exception:
                    switches = 0
                try:
                    affinity = list(self._proc.cpu_affinity())
                except Exception:
                    affinity = []
                try:
                    times = self._proc.cpu_times()
                    user_s = float(times.user)
                    system_s = float(times.system)
                except Exception:
                    user_s = 0.0
                    system_s = 0.0
            self._peak_rss = max(self._peak_rss, rss)
            wall_ms = max(0.0, (time.monotonic() - self._start_wall) * 1000.0)
            freq = 0.0
            try:
                f = self._psutil.cpu_freq()
                if f is not None:
                    freq = float(f.current or 0.0)
            except Exception:
                freq = 0.0
            flags = detect_cpu_flags()
            values: dict[str, float] = {
                "cpu.usage_percent": cpu,
                "cpu.wall_time_ms": wall_ms,
                "cpu.cpu_time_seconds": user_s + system_s,
                "cpu.user_time_seconds": user_s,
                "cpu.system_time_seconds": system_s,
                "cpu.thread_count": float(threads),
                "cpu.context_switches": float(switches),
                "cpu.frequency_mhz": freq,
                "cpu.core_utilization": cpu,
                "memory.rss_bytes": rss,
                "memory.vms_bytes": vms,
                "memory.peak_rss_bytes": self._peak_rss or rss,
                "memory.average_rss_bytes": rss,
                "memory.percent": float(self._proc.memory_percent()),
                "numa.node": 0.0,
                "hardware.sve2_available": 1.0 if "sve2" in flags else 0.0,
                "hardware.i8mm_available": 1.0 if "i8mm" in flags else 0.0,
            }
            for i, core in enumerate(affinity[:64]):
                values[f"cpu.affinity.{i}"] = float(core)
            batch = samples_from_mapping(self.name, session, values)
            return batch
        except Exception as exc:
            self._mark_failure(exc)
            return empty_batch(self.name, session)
