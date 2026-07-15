"""Deterministic mock profiler — always available for CI / degrade path."""

from __future__ import annotations

import hashlib
import time

from ..schemas import (
    CapabilityState,
    MetricBatch,
    ProfileSessionContext,
    ProviderCapabilities,
)
from .base import BaseProfilerProvider, samples_from_mapping


class MockProfilerProvider(BaseProfilerProvider):
    name = "mock"

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name=self.name,
            available=True,
            state=CapabilityState.AVAILABLE,
            sampling=True,
            tracing=False,
            cpu=True,
            memory=True,
            hardware=True,
            continuous=False,
            reasons=("deterministic synthetic metrics",),
        )

    def sample(self, session: ProfileSessionContext) -> MetricBatch:
        seed = hashlib.sha256(
            f"{session.session_id}:{session.request_id}".encode()
        ).hexdigest()
        n = int(seed[:8], 16)
        wall = max(0.0, (time.monotonic() % 7.0) * 10.0)
        cpu = 5.0 + (n % 40)
        rss = 128 * 1024 * 1024 + (n % 64) * 1024 * 1024
        cycles = 1_000_000.0 + (n % 500_000)
        instr = cycles * (1.1 + (n % 50) / 100.0)
        return samples_from_mapping(
            self.name,
            session,
            {
                "cpu.usage_percent": cpu,
                "cpu.wall_time_ms": wall,
                "cpu.cpu_time_seconds": wall / 1000.0 * (cpu / 100.0),
                "cpu.user_time_seconds": wall / 1000.0 * 0.7,
                "cpu.system_time_seconds": wall / 1000.0 * 0.3,
                "cpu.thread_count": float(2 + (n % 6)),
                "cpu.context_switches": float(100 + (n % 900)),
                "memory.rss_bytes": float(rss),
                "memory.vms_bytes": float(rss * 1.5),
                "memory.peak_rss_bytes": float(rss * 1.1),
                "memory.average_rss_bytes": float(rss),
                "hardware.cycles": cycles,
                "hardware.instructions": instr,
                "hardware.ipc": instr / cycles if cycles else 0.0,
                "hardware.cache_misses": float(1000 + (n % 5000)),
                "hardware.branch_misses": float(200 + (n % 800)),
                "numa.node": 0.0,
            },
        )
