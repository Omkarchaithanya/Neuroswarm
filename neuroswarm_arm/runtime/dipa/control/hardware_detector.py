"""ControlHardwareDetector — rich CPU/NUMA/cache profile for DIPA + build."""

from __future__ import annotations

import os
import platform
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class HardwareProfile:
    arch: str
    cpu_count: int
    features: dict[str, bool] = field(default_factory=dict)
    numa_nodes: int = 1
    cache_sizes_kb: dict[str, int] = field(default_factory=dict)
    model_name: str = ""
    thread_count: int = 0
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "arch": self.arch,
            "cpu_count": self.cpu_count,
            "thread_count": self.thread_count,
            "features": dict(self.features),
            "numa_nodes": self.numa_nodes,
            "cache_sizes_kb": dict(self.cache_sizes_kb),
            "model_name": self.model_name,
            "raw": dict(self.raw),
        }


class ControlHardwareDetector:
    """Detect SVE2 / DotProd / I8MM / SME / BF16 / NUMA / caches at runtime."""

    FEATURE_TOKENS = {
        "sve": ("sve",),
        "sve2": ("sve2",),
        "dotprod": ("asimddp", "dotprod"),
        "i8mm": ("i8mm",),
        "sme": ("sme",),
        "sme2": ("sme2",),
        "bf16": ("bf16",),
        "asimd": ("asimd", "neon"),
        "mte": ("mte",),
    }

    def detect(self) -> HardwareProfile:
        arch = platform.machine().lower() or "unknown"
        cpu_count = os.cpu_count() or 1
        features = {k: False for k in self.FEATURE_TOKENS}
        model_name = ""
        cpuinfo = Path("/proc/cpuinfo")
        text = ""
        if cpuinfo.exists():
            text = cpuinfo.read_text(encoding="utf-8", errors="ignore")
            lower = text.lower()
            for feat, tokens in self.FEATURE_TOKENS.items():
                features[feat] = any(t in lower for t in tokens)
            for line in text.splitlines():
                if line.lower().startswith("model name") or line.lower().startswith(
                    "cpu part"
                ):
                    model_name = line.split(":", 1)[-1].strip()
                    break
        # Windows / non-Linux: leave features false unless ARM64 host.
        if not text and arch in {"aarch64", "arm64"}:
            features["asimd"] = True

        numa_nodes = self._detect_numa()
        caches = self._detect_caches()
        return HardwareProfile(
            arch=arch,
            cpu_count=cpu_count,
            features=features,
            numa_nodes=numa_nodes,
            cache_sizes_kb=caches,
            model_name=model_name,
            thread_count=cpu_count,
            raw={"platform": platform.platform(), "processor": platform.processor()},
        )

    def _detect_numa(self) -> int:
        base = Path("/sys/devices/system/node")
        if base.exists():
            nodes = [p for p in base.iterdir() if p.name.startswith("node")]
            return max(1, len(nodes))
        return 1

    def _detect_caches(self) -> dict[str, int]:
        out: dict[str, int] = {}
        cpu0 = Path("/sys/devices/system/cpu/cpu0/cache")
        if not cpu0.exists():
            return out
        for index in cpu0.glob("index*"):
            try:
                level = (index / "level").read_text().strip()
                size = (index / "size").read_text().strip().lower()
                typ = (index / "type").read_text().strip().lower()
                kb = _parse_size_kb(size)
                key = f"L{level}_{typ}"
                out[key] = kb
            except Exception:
                continue
        return out


def _parse_size_kb(size: str) -> int:
    m = re.match(r"(\d+)([kmg]?)b?", size.strip().lower())
    if not m:
        return 0
    n = int(m.group(1))
    unit = m.group(2)
    if unit == "k":
        return n
    if unit == "m":
        return n * 1024
    if unit == "g":
        return n * 1024 * 1024
    return n
