"""Linux perf provider — best-effort subprocess sampling; never mandatory."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from typing import Any

from ..schemas import (
    CapabilityState,
    MetricBatch,
    ProfileSessionContext,
    ProviderCapabilities,
)
from .base import (
    BaseProfilerProvider,
    detect_cpu_flags,
    empty_batch,
    is_linux,
    samples_from_mapping,
    which_binary,
)

logger = logging.getLogger(__name__)

_PERF_EVENTS = (
    "cycles",
    "instructions",
    "cache-misses",
    "cache-references",
    "branch-misses",
    "branch-instructions",
)


class PerfProfilerProvider(BaseProfilerProvider):
    name = "perf"

    def __init__(self) -> None:
        super().__init__()
        self._perf = which_binary("perf")
        self._pid = os.getpid()

    def capabilities(self) -> ProviderCapabilities:
        ok = is_linux() and self._perf is not None
        reasons: list[str] = []
        if not is_linux():
            reasons.append("perf requires Linux")
        if self._perf is None:
            reasons.append("perf binary not on PATH")
        return ProviderCapabilities(
            name=self.name,
            available=ok,
            state=CapabilityState.AVAILABLE if ok else CapabilityState.UNAVAILABLE,
            sampling=ok,
            tracing=False,
            cpu=ok,
            memory=False,
            hardware=ok,
            continuous=False,
            reasons=tuple(reasons),
            extensions={"cpu_flags": sorted(detect_cpu_flags())},
        )

    def sample(self, session: ProfileSessionContext) -> MetricBatch:
        if not self.capabilities().available or self._perf is None:
            return empty_batch(self.name, session)
        try:
            cmd = [
                self._perf,
                "stat",
                "-j",
                "-e",
                ",".join(_PERF_EVENTS),
                "-p",
                str(self._pid),
                "--",
                "sleep",
                "0.05",
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            values = self._parse_perf_output(result.stdout + "\n" + result.stderr)
            if not values:
                return empty_batch(self.name, session)
            cycles = values.get("hardware.cycles", 0.0)
            instr = values.get("hardware.instructions", 0.0)
            if cycles > 0 and "hardware.ipc" not in values:
                values["hardware.ipc"] = instr / cycles
            flags = detect_cpu_flags()
            values["hardware.sve2_available"] = 1.0 if "sve2" in flags else 0.0
            values["hardware.i8mm_available"] = 1.0 if "i8mm" in flags else 0.0
            values["hardware.pmu_available"] = 1.0
            return samples_from_mapping(self.name, session, values)
        except Exception as exc:
            self._mark_failure(exc)
            return empty_batch(self.name, session)

    def _parse_perf_output(self, text: str) -> dict[str, float]:
        values: dict[str, float] = {}
        # JSON lines from `perf stat -j`
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                obj: dict[str, Any] = json.loads(line)
            except Exception:
                continue
            event = str(obj.get("event") or obj.get("event_name") or "").lower()
            counter = obj.get("counter-value") or obj.get("counter_value") or obj.get("value")
            if counter is None:
                continue
            try:
                num = float(str(counter).replace(",", ""))
            except Exception:
                continue
            key = self._map_event(event)
            if key:
                values[key] = num
        if values:
            return values
        # Fallback text parse
        patterns = {
            "hardware.cycles": r"([\d,]+)\s+cycles",
            "hardware.instructions": r"([\d,]+)\s+instructions",
            "hardware.cache_misses": r"([\d,]+)\s+cache-misses",
            "hardware.cache_references": r"([\d,]+)\s+cache-references",
            "hardware.branch_misses": r"([\d,]+)\s+branch-misses",
            "hardware.branch_instructions": r"([\d,]+)\s+branch-instructions",
        }
        for key, pat in patterns.items():
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                try:
                    values[key] = float(m.group(1).replace(",", ""))
                except Exception:
                    pass
        return values

    @staticmethod
    def _map_event(event: str) -> str | None:
        mapping = {
            "cycles": "hardware.cycles",
            "instructions": "hardware.instructions",
            "cache-misses": "hardware.cache_misses",
            "cache-references": "hardware.cache_references",
            "branch-misses": "hardware.branch_misses",
            "branch-instructions": "hardware.branch_instructions",
        }
        for suffix, key in mapping.items():
            if event.endswith(suffix) or suffix in event:
                return key
        return None
